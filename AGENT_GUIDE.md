# 实现指南：`tools.py` 与 `agent.py`

> 这份文件**只讲你亲手写的那两个文件**。其余通用件已就绪（`types` / `logparse` / `kb` / `llm` / `trace` / `report` / `cli`），
> 数据契约与设计取舍见 [ARCHITECTURE.md](ARCHITECTURE.md) §3–§5。

## 0. 先记住三句话

1. **模型负责「做什么」，代码负责「边界」** —— 调哪个工具、query 怎么写、够不够、何时收尾，是模型决定；步数上限、防死循环、引用校验，是代码决定。
2. **工具永不抛异常** —— 出错就返回一句人话给模型，让它自己改策略。抛异常 = 循环崩掉。
3. **收尾不解析文本** —— 用 `tool_choice` 强制模型调 `finish`，报告直接来自它的参数。

---

## 1. `tools.py`

### 1.1 结构（就三段）

```python
TOOL_SCHEMAS = [...]          # 给模型看的工具清单（自动喂给 llm.chat(tools=...)）
FINISH_SCHEMA = {...}         # 单独拿一份，收尾时用 tool_choice 强制它

def dispatch(name: str, args: dict) -> tuple[str, list[RetrievedDoc]]:
    """执行工具。返回 (给模型看的文本, 本次检索到的文档)。未知工具/内部异常都返回人话，不抛。"""
```

**为什么 `dispatch` 要返回 `docs`**：引用校验需要「本轮检索集合」。让工具把命中的文档交出来，
agent 自己维护 `retrieved` 字典——**工具保持纯函数，不碰状态**。

### 1.2 `TOOL_SCHEMAS`（可以直接抄，但要理解 description 为什么这么写）

```python
from uediag.types import cfg_int

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "在 UE 排障知识库里检索同类案例。**不确定根因时必须先调用它，不要凭记忆回答。**"
                "query 里要保留错误码原文（例如 LNK2019、EXCEPTION_ACCESS_VIOLATION），不要改写或翻译它们。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词：错误码 + 模块名 + 现象，中英文都可以"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 3", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_screenshot",
            "description": (
                "查看用户提供的截图。会在内部调用视觉模型做信息抽取，返回纯文本。"
                "当日志证据不足、或用户说「看截图」时必须调用。"
                "输入必须是上面给出的可用截图路径，不要自己编路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "image_ref": {"type": "string", "description": "可用截图路径（原样传，不要改）"},
                    "question": {"type": "string", "description": "你想从图里确认什么，例如「弹窗里的错误码是什么」"},
                },
                "required": ["image_ref", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "诊断完成，提交结构化结论。**证据不足时也要调用它**——把 confidence 填 low 并在 summary 里"
                "说明「知识库未覆盖」，不要编造修复步骤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string",
                                 "enum": ["crash", "compile", "build", "cook", "asset", "perf", "unknown"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "summary": {"type": "string", "description": "一句话结论，说给非技术同学听"},
                    "root_cause": {"type": "string", "description": "根因；不确定就写「暂无法确定」"},
                    "fix_steps": {"type": "array", "items": {"type": "string"},
                                  "description": "按顺序的修复步骤，给到具体菜单路径"},
                    "escalate_to": {"type": "string", "description": "该找谁：程序组 / TA / 构建机"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"},
                                      "description": "依据的 case 编号，如 UE-ERR-0002；只能用检索结果里出现过的"},
                },
                "required": ["category", "confidence", "summary", "root_cause", "fix_steps", "evidence_refs"],
            },
        },
    },
]

FINISH_SCHEMA = TOOL_SCHEMAS[-1]      # 收尾时单独用
```

**三条 description 的写法要点**（这是规划的真正杠杆）：

| 写法 | 为什么 |
|---|---|
| `search_kb` 里强调「不确定必须先调用」 | 不写这句，模型会凭通用知识直接答，RAG 就白做了 |
| `search_kb` 里强调「保留错误码原文」 | 模型很爱把 `LNK2019` 改写成「链接错误」，**一改写检索就废了** |
| `finish` 里强调「证据不足也要调」 | 否则它会卡住不说结论，或在正文里写一大段非结构化的话 |

### 1.3 `dispatch` 实现

```python
import json
from uediag import llm
from uediag.kb import search_kb
from uediag.types import RetrievedDoc, cfg_int


def dispatch(name: str, args: dict) -> tuple[str, list[RetrievedDoc]]:
    try:
        if name == "search_kb":
            return _search_kb(args), _LAST_DOCS
        if name == "read_screenshot":
            return _read_screenshot(args), []
        return f"未知工具 {name}，可用工具：search_kb / read_screenshot / finish。", []
    except Exception as e:                      # 兜住一切：工具永不抛给循环
        return f"工具 {name} 执行失败：{type(e).__name__}: {e}。请换个方式重试，或直接 finish。", []
```

> `_LAST_DOCS` 只是示意 —— 更好的写法是让 `_search_kb` 直接返回 `(文本, docs)` 元组，
> 别用模块级变量存状态（下面 1.4 就是这么写的）。

### 1.4 三个工具的实现要点

**`search_kb` —— observation 的格式直接决定模型下一步质量**

```python
def _search_kb(args: dict) -> tuple[str, list[RetrievedDoc]]:
    query = str(args.get("query") or "").strip()
    if not query:
        return "query 不能为空。请把错误码和现象一起写进 query。", []
    k = int(args.get("top_k") or cfg_int("TOP_K"))
    docs = search_kb(query, top_k=k)              # ← 通用件里的函数
    if not docs:
        return (f"知识库没有任何命中（query={query!r}）。"
                f"可以换关键词再试一次，或直接 finish 并在 summary 里说明知识库未覆盖。", [])
    lines = [f"命中 {len(docs)} 条："]
    for i, d in enumerate(docs, 1):
        lines.append(f"\n{i}. [{d.doc_id}] {d.title}（score={d.score:.4f}）\n{d.body}")
    lines.append("\n提示：引用时只能写上面出现过的编号；需要更多线索可以换关键词再查一次。")
    return "\n".join(lines), docs
```

- **返回全文**（不用再做 `get_doc`）——case 都很短
- **结尾加一句行动建议**，模型的下一步质量会明显提升
- **零命中时给出口**（换关键词 / 或 finish 并声明未覆盖），否则模型容易开始编

**`read_screenshot` —— 只做文本转述，不要让它顺手诊断**

```python
def _read_screenshot(args: dict) -> tuple[str, list[RetrievedDoc]]:
    ref = str(args.get("image_ref") or "").strip()
    question = str(args.get("question") or "这张图里报了什么错？")
    text = llm.describe_image(ref, question)       # ← 通用件：内部单轮调视觉模型
    if not text:
        return f"截图 {ref} 没有读到内容，可能是图片损坏。可以跳过截图，用日志继续诊断。", []
    return f"截图信息（来自视觉模型，仅客观抽取，不含结论）：\n{text}", []
```

- 视觉模型**不参与规划**，返回的只有客观信息；根因判断仍然由规划模型 + 知识库完成
- 把 `uncertainty` 原样带回来 —— 它会变成给用户的追问，而不是编造的答案

**`finish` —— 不执行任何事**

```python
# dispatch 里不用处理 finish：agent 检测到 name == "finish" 就自己收尾了
# 参数解析统一走：DiagnosisReport.from_tool_args(args, trace_id)
```

### 1.5 写完先这样自检（不花一分钱、不调模型）

```bash
python -c "from uediag import tools; print(tools.dispatch('search_kb', {'query':'LNK2019'})[0][:300])"
python -c "from uediag import tools; print(tools.dispatch('no_such_tool', {})[0])"
python -c "from uediag import tools; print([t['function']['name'] for t in tools.TOOL_SCHEMAS])"
```

第二条必须返回一句人话且**不抛异常**——这是循环健壮性的第一道门。

---

## 2. `agent.py`

### 2.1 骨架（照着填，注释里是「为什么」）

```python
from __future__ import annotations

from uediag import llm, tools
from uediag.logparse import clean_log
from uediag.trace import TraceRecorder
from uediag.types import DiagnosisReport, Evidence, RetrievedDoc, cfg, cfg_int

SYSTEM = """你是 UE5 项目排障助手，服务对象是策划/美术/QA 和技术新人。

**始终用中文回答**（模型默认可能用英文，必须明确要求）。

铁律：
1. 不确定根因时**必须先调 search_kb**，不要凭记忆回答。
2. 检索 query 里保留错误码原文（LNK2019、C2065、EXCEPTION_ACCESS_VIOLATION），不要改写。
3. 报告里的 evidence_refs 只能填检索结果中出现过的编号；没有依据就写空数组。
4. 知识库没覆盖就直说，confidence 填 low，不要编造修复步骤。
5. 修复步骤要给到具体菜单路径（例如「内容浏览器 → /Game/Blueprints/BP_Tank → 事件图表」）。
6. 结论准备好后调用 finish。"""


def run(log_path: str | None = None, image_path: str | None = None, note: str = "") -> DiagnosisReport:
    llm.reset_usage()
    tr = TraceRecorder()

    # ① 轮 0：规则抽取，不花 LLM 钱
    evidence = clean_log(log_path) if log_path else Evidence()
    tr.perceive(evidence)

    # ② 组装首条 user 消息：只给「证据 + 可用截图路径」，图片本身不进上下文
    parts = []
    if note:
        parts.append(f"用户描述：{note}")
    parts.append(evidence.render())
    if image_path:
        parts.append(f"可用截图：{image_path}（要查看请调用 read_screenshot）")
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]

    retrieved: dict[str, RetrievedDoc] = {}
    report: DiagnosisReport | None = None

    # ③ 主循环：每一轮 = 一次规划决策
    for _ in range(cfg_int("MAX_STEPS")):
        before = llm.usage()
        with llm.Timer() as t:
            msg = llm.chat(messages, tools=tools.TOOL_SCHEMAS)      # model 默认 MODEL_TEXT
        after = llm.usage()

        # assistant 消息必须原样回传（含 tool_calls），否则下一轮的 tool 消息无法配对
        messages.append(llm.as_message_dict(msg))

        tr.step(phase="plan", action=(msg.tool_calls[0].function.name if msg.tool_calls else None),
                observation=(msg.content or "")[:200], model=cfg("MODEL_TEXT"), latency_ms=t.ms,
                tokens_in=after["in"] - before["in"], tokens_out=after["out"] - before["out"],
                cost_cny=after["cost"] - before["cost"])

        if not msg.tool_calls:                       # 模型想直接说话 → 逼它用 finish
            messages.append({"role": "user", "content": "请调用 finish 输出结构化结论。"})
            continue

        for call in msg.tool_calls:                  # 一次可能返回多个，全都要回
            name = call.function.name
            args = llm.tool_args(call)
            if name == "finish":
                report = DiagnosisReport.from_tool_args(args, tr.trace_id)
                break
            obs, docs = tools.dispatch(name, args)
            retrieved.update({d.doc_id: d for d in docs})
            messages.append(llm.tool_reply(call.id, obs))        # tool_call_id 严格配对
            tr.step(phase="act", action=name, args=args, observation=obs, model=cfg("MODEL_TEXT"))

        if report:
            break
    else:
        # ④ 预算耗尽：注入收敛指令，保证永远有产出
        messages.append({"role": "user", "content": "步数预算已用尽，请基于现有证据调用 finish。"})

    # ⑤ 收尾：用 tool_choice 强制 finish，报告直接来自工具参数（不解析自由文本）
    if report is None:
        msg = llm.chat(messages, tools=[tools.FINISH_SCHEMA],
                       tool_choice={"type": "function", "function": {"name": "finish"}})
        args = llm.tool_args(msg.tool_calls[0]) if msg.tool_calls else {}
        report = DiagnosisReport.from_tool_args(args, tr.trace_id)

    # ⑥ 防幻觉 + 补上下文
    report = validate_refs(report, retrieved)
    report.trace_id = tr.trace_id
    report.cost_cny = llm.usage()["cost"]
    report._docs = list(retrieved.values())          # 可选：让 CLI/UI 显示引用标题
    tr.finish(report)
    return report


def validate_refs(report: DiagnosisReport, retrieved: dict) -> DiagnosisReport:
    """引用必须 ⊆ 本次检索集合。不实的剔除；空了就降置信度并说明。"""
    kept = [r for r in report.evidence_refs if r in retrieved]
    dropped = [r for r in report.evidence_refs if r not in retrieved]
    report.evidence_refs = kept
    if dropped:
        print(f"[警告] 模型引用了不存在的 case，已剔除：{dropped}")
    if not kept:
        report.confidence = "low"
        note = "知识库未覆盖该问题，以上结论仅供参考，建议直接找程序确认。"
        report.summary = (report.summary + " " + note).strip()
    return report
```

### 2.2 七个必须踩对的点（错了会怎样）

| # | 点 | 错了会怎样 |
|---|---|---|
| 1 | `messages.append(llm.as_message_dict(msg))` **原样回传** | 下一轮 `role="tool"` 找不到对应的 `tool_call_id` → **400** |
| 2 | 每个 `tool_calls[i]` 都要回一条 `llm.tool_reply(call.id, ...)` | 漏一条就 400；id 写错也是 400 |
| 3 | 一次响应的多个 `tool_calls` **全部执行**后再进下一轮 | 只处理第一个 → 协议不完整 → 400 |
| 4 | 参数用 `llm.tool_args(call)` 容错解析 | 直接 `json.loads` → 模型给个非法 JSON 就崩 |
| 5 | 工具异常吞掉、返回人话 | 抛出去 → 整个诊断崩，trace 也就断了 |
| 6 | 收尾用 `tool_choice` 强制 `finish` | 靠解析正文 → 格式随机，报告字段缺一半 |
| 7 | 收尾时**仍然用 `MODEL_TEXT`** | 换成别的模型会丢掉整个对话上下文 |
| 8 | system prompt 里**明确要求中文** | 模型会用英文答复（实测会），面向策划/美术的演示直接翻车 |

### 2.2.1 思考模式的坑（**已经替你趟过，别踩第二次**）

`deepseek-v4-flash` **默认开思考模式**，而它有两个硬约束（官方文档 + 实测）：

| 约束 | 后果 |
|---|---|
| 思考模式下**不支持指定函数的 `tool_choice`** | 报 `400 Thinking mode does not support this tool_choice` → **第 6 条收尾策略直接失效** |
| 带 `tools` 的请求，后续每轮**必须完整回传 `reasoning_content`** | 漏了 → 400（`llm.as_message_dict()` 已经帮你带上） |
| 思考模式下 `temperature` 被忽略 | 调参白调 |

所以默认配置是 **`THINKING=disabled`**：能强制 `finish`、结果可复现、更快更便宜。
如果你想开思考模式（复杂日志的推理质量确实更好），**必须同时改两处**：

1. `.env` 里 `THINKING=enabled`
2. 收尾别再用 `tool_choice` 指定函数 —— 改成「只传 `FINISH_SCHEMA` + 追加一条『请调用 finish』的 user 消息」，靠约束而非强制

### 2.3 引用校验为什么必须写在 agent 里

它是**唯一一个「模型说了不算」的地方**：模型可以编一个 `UE-ERR-9999`，但 `retrieved` 里没有，就直接剔除。
空引用 → 置信度降 `low` → 报告里明说「知识库未覆盖」。**这一条是整套防幻觉机制的核心**，10 行代码。

### 2.4 自检顺序（每一步都别跳）

```bash
# 1) 工具层：不经模型，直接调
python -c "from uediag import tools; print(tools.dispatch('search_kb', {'query':'开火就崩'})[0][:200])"

# 2) 一次真实调用：确认 key / base_url / tool calling 都通
python -c "from uediag import llm; s={'type':'function','function':{'name':'finish','description':'提交结论','parameters':{'type':'object','properties':{'summary':{'type':'string'}},'required':['summary']}}}; m=llm.chat([{'role':'user','content':'调用 finish，summary 写 ok'}], tools=[s], tool_choice={'type':'function','function':{'name':'finish'}}); print(m.tool_calls[0].function.name, llm.tool_args(m.tool_calls[0]))"

# 3) 完整链路
python -m uediag diagnose --log data/samples/crash_demo.log --print-trace
```

第 2 步是关键分水岭：**它过了，说明模型、鉴权、工具协议三件事都对**，再调 agent 逻辑就不会误判方向。

---

## 3. 调试手册（症状 → 病因）

| 症状 | 病因 | 怎么办 |
|---|---|---|
| `401 Invalid API key` | `.env` 里的 key 或 `OPENAI_API_URL` 不对 | `python -c "from uediag.types import ensure_env,cfg; ensure_env(); print(cfg('OPENAI_API_URL'), cfg('OPENAI_API_KEY')[:8])"` |
| `400 Thinking mode does not support this tool_choice` | 开了思考模式还想强制 `tool_choice` | `.env` 设 `THINKING=disabled`（默认就是） |
| `400`（第二轮才出现，提到 `reasoning_content`） | 思考模式下没回传 `reasoning_content` | 用 `llm.as_message_dict(msg)`，别自己拼 dict |
| `400 ... tool_call_id` | assistant 消息没原样回传，或漏回某个 `tool_call` | 检查 §2.2 的 1/2/3 条 |
| 模型一直不调工具、只说话 | system prompt 里没强调「先检索」；或工具 description 太弱 | 抄 1.2 的 description |
| 模型用英文回答 | system prompt 没要求中文 | 加「始终用中文回答」（§2.2 第 8 条） |
| 模型把 `LNK2019` 改写成「链接错误」 | query 生成时改写了符号 | 在 description 和 system 里都强调「保留错误码原文」 |
| 模型搜了一次就停、直接编结论 | `finish` 的 description 没强调「证据不足也要调」 | 抄 1.2 的 finish description |
| 无限循环调同一个工具 | 没有防死循环守卫 | 用 `(工具, 参数)` 计数，≥2 次就回「请换策略」 |
| `Collection expecting embedding with dimension of 256, got 1024` | 换过 `EMBED_BACKEND` 但没重建集合 | 跑 `python -m uediag kb rebuild`（会自动重建） |
| 检索全空 | 没入库，或 `KNOWLEDGE_DIR` 写错 | `python -m uediag kb check` |
| 中文乱码 | 控制台是 GBK | CLI 已处理；自己写脚本时加 `sys.stdout.reconfigure(encoding="utf-8")` |

---

## 4. 从零到跑通的最短路径

```bash
python -m uediag kb rebuild                              # 1) 入库（真模型，~30 秒）
python tests/accept_retrieval.py                          # 2) 检索验收 8/8
python -c "from uediag import tools; print(tools.dispatch('search_kb',{'query':'LNK2019'})[0][:200])"   # 3) 工具层
python -m uediag diagnose --log data/samples/crash_demo.log --print-trace   # 4) 端到端
```

---

## 5. 有余力再加（都不影响已有代码）

1. **防死循环守卫**：`(工具名, 参数哈希)` 连续失败 2 次 → 拦截并提示换策略
2. **观测截断**：`tr.step` 里已经截了；如果你想控制得更细，用 `cfg_int("MAX_OBSERVATION_CHARS")`
3. **参数校验自纠**：`args` 缺 `query` 就别调工具，直接回「query 不能为空」
4. **反例清单**：报告里出现「重装引擎」这类无脑建议时，在 `validate_refs` 里顺手打个警告
5. **截图 + 日志混合**：现在两条路都通了，`run(log_path=..., image_path=...)` 直接支持
