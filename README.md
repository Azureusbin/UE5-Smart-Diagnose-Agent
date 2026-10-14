# UE5 智诊助手

贴一段 UE 日志或一张报错截图，Agent 自己规划要查什么，从知识库检索同类案例，
输出「是什么问题 / 根因 / 怎么修 / 该找谁 / 依据哪篇 case」。

- 规划：原生 **Function Calling**（模型产出 `tool_calls` → 执行 → `role="tool"` 回传）
- 检索：**双轨 RAG**（BM25 稀疏 + Chroma/BGE-M3 稠密 → RRF 融合）
- 多模态：视觉模型**只读图出结构化信息**，不参与规划
- 防幻觉：报告引用必须 ⊆ 本次检索集合，否则剔除并降置信度

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 5 分钟跑起来

```bash
pip install -r requirements.txt

# 0) 取嵌入模型权重（约 2.1 GB，一次就够；支持断点续传）
python -m uediag.fetch_model
```

> **为什么要这一步**：权重需要预先拉到本地，之后才能完全离线加载。
> `uediag/fetch_model.py` 从魔搭（ModelScope）下载到 `models/bge-m3/`，BAAI 官方也在上面发布，国内直连。
> 想用别的位置：`python -m uediag.fetch_model --dir D:\models\bge-m3`，并同步改 `.env` 的 `EMBED_MODEL`。

首次运行任何命令都会**自动生成 `.env`**，去里面填上 `OPENAI_API_KEY` 即可（其余项都有默认值）。

```bash
# 1) 知识库入库（第一次会加载本地权重并编码 5 条 case）
python -m uediag kb rebuild

# 2) 只跑检索：不调 LLM、不花钱
python -m uediag kb search "开火就崩"
python -m uediag kb search "error LNK2019 unresolved external symbol"

# 3) 只跑日志收敛：看 clean_log 把日志压成什么样
python -m uediag log show data/samples/crash_demo.log

# 4) 完整链路（需要 agent.py，见下）
python -m uediag diagnose --log data/samples/crash_demo.log --print-trace

# 5) 检索验收（约 0.05 秒，改完知识库顺手跑一次）
python tests/accept_retrieval.py

# 6) Web UI（浏览器演示用；左上传 / 中报告 / 右 trace）
python -m streamlit run uediag/web.py --server.address 127.0.0.1
```

## 配置

`.env` 由程序自动生成，**已存在就绝不覆盖**。改参数直接改它；缺项会自动回落到
`uediag/types.py` 里的 `DEFAULTS`。唯一必填的是 `OPENAI_API_KEY`。

| 变量 | 默认 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | — | **必填** |
| `OPENAI_API_URL` | `https://api.deepseek.com` | SDK 默认找的是 `OPENAI_BASE_URL`，所以代码里显式传 `base_url` |
| `MODEL_TEXT` | `deepseek-v4-flash` | 规划 / Function Calling / 报告 |
| `MODEL_VISION` | `deepseek-v4-flash-vision-exp` | 只读图出结构化信息 |
| `THINKING` | `disabled` | 思考模式开关。**开着就不支持指定函数的 `tool_choice`**（收尾无法强制 `finish`），且每轮必须回传 `reasoning_content`。 |
| `REASONING_EFFORT` | `high` | 仅 `THINKING=enabled` 时生效：`low`/`high`/`max` |
| `MAX_STEPS` | `6` | 唯一的预算闸 |
| `MAX_OBSERVATION_CHARS` | `1200` | 单条工具结果截断 |
| `TOP_K` / `RRF_K` | `3` / `60` | 检索条数与融合参数 |
| `RETRIEVER` | `hybrid` | `hybrid`（BM25+向量）/ `vector`（只要向量）/ **`bm25`（不加载模型、不访问向量库，0.1 秒启动）** |
| `EMBED_BACKEND` | `local` | `local`（真模型）或 `mock`（哈希伪向量，离线单测用） |
| `EMBED_MODEL` | `./models/bge-m3` | 本地权重目录（由 `uediag/fetch_model.py` 准备） |
| `CHROMA_PATH` / `KNOWLEDGE_DIR` / `TRACE_DIR` | `./.chroma` / `./knowledge/ue_errors` / `./runs` | 路径 |

> 换过 `EMBED_BACKEND` / `EMBED_MODEL` 之后跑一次 `kb rebuild`：程序会检测到编码方式变化并**自动重建集合**（向量维度不同，不能混用）。

---

## 目录与分工

```
uediag/
├─ types.py     数据契约 Evidence / RetrievedDoc / DiagnosisReport + 配置
├─ logparse.py  clean_log()：日志收敛
├─ kb.py        知识库：加载 / 编码 / 入库 / 双轨检索
├─ llm.py       模型客户端（文本 + 视觉）+ 花费记账
├─ trace.py     轨迹记录与时间线打印
├─ report.py    报告渲染
├─ cli.py       命令行入口
├─ tools.py     3 个工具 + schema（search_kb / read_screenshot / finish）
├─ agent.py     Function Calling 循环
├─ web.py       Web UI：左侧上传 · 右侧 Tab 切换「诊断报告 / Agent 轨迹」
└─ fetch_model.py  从魔搭拉 BGE-M3 权重（python -m uediag.fetch_model）
```

### Web UI

```bash
python -m streamlit run uediag/web.py --server.address 127.0.0.1
```

> 用 `python -m streamlit` 而不是裸 `streamlit`：后者要求 `Scripts/` 在 PATH 上，很多环境里没有。
> `--server.address 127.0.0.1` 是让它只监听本机，不加会绑 `0.0.0.0`（局域网/公网可访问）。

左栏是**一个多选拖拽区**：日志（`.log`/`.txt`）和报错截图可以一起拖进去，程序按后缀/MIME
自动分流，日志会兼容 UTF-8 / UTF-16 / GBK 编码（多个日志按顺序合并）。下面一句话描述可选。
中栏出报告（可下载 Markdown / 看原始 JSON），右栏是逐步展开的 trace 时间线 —— 每一步的
工具、参数、观察结果、耗时与花费都能点开看。**看不看截图由模型自己决定**：它认为日志证据
不够时会主动调 `read_screenshot`。

> **权重在打开页面时就加载**（用 `st.cache_resource` 缓存）：第一次进页面会转十几秒加载 BGE-M3，
> 之后就绪，点「开始诊断」不再等模型。权重缺失时页面照常渲染，只提示去跑 `uediag/fetch_model.py`。

### 三个工具

三个工具 + JSON Schema，供 `llm.chat(..., tools=...)` 使用：

| 工具 | 参数 | 内部实现 |
|---|---|---|
| `search_kb` | `query`, `top_k=3` | 调 `kb.search_kb(query, top_k)` |
| `read_screenshot` | `image_ref`, `question` | 调 `llm.describe_image(path, question)`，返回纯文本 |
| `finish` | 报告字段（= `DiagnosisReport`） | 返回终止信号；参数用 `DiagnosisReport.from_tool_args()` 解析 |

### `uediag/agent.py`

```python
def run(log_path=None, image_path=None, note="") -> DiagnosisReport:
    ...
```

要点（细节见 ARCHITECTURE.md §5）：

1. 先 `clean_log(log_path)` 拿 `Evidence`，`TraceRecorder()` 记第一步
2. 循环 `llm.chat(messages, tools=TOOL_SCHEMAS, model=cfg("MODEL_TEXT"))`
3. **assistant 消息必须原样回传**（用 `llm.as_message_dict`），每个 `tool_calls` 都要回一条 `llm.tool_reply`
4. 最多 `MAX_STEPS` 步；耗尽则注入「基于现有证据出结论」并强制 `finish`
5. 收尾用 `tool_choice={"type":"function","function":{"name":"finish"}}` 拿结构化报告
6. **引用校验**：`report.evidence_refs` 必须 ⊆ 本次检索集合，不实的剔除；为空则 `confidence="low"`
7. `report.trace_id = tr.trace_id`、`report.cost_cny = llm.usage()["cost"]`
8. 可选：`report._docs = 本次检索到的 RetrievedDoc 列表` —— CLI/UI 靠它把 `[UE-ERR-0002]` 渲染成带标题和出处的引用（不设也能跑，只是引用只有编号）

写完就能跑：

```bash
python -m uediag diagnose --log data/samples/crash_demo.log --image shot.png --print-trace
```

---

## Windows 提示

控制台默认 GBK，CLI 已把输出统一切到 UTF-8。如果中文仍显示乱码，在终端执行一次：

```powershell
chcp 65001
```

或设环境变量 `PYTHONUTF8=1`。

