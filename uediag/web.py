"""UE5 智诊助手 · Streamlit Web UI

单文件外壳：**只做「收输入 → 调 agent.run → 渲染产物」**，任何业务判断都不在这里
（和 cli.py 一样，两个外壳复用同一批函数）。

    streamlit run uediag/web.py

版面（见 ARCHITECTURE.md §1）：左侧上传 · 右侧用 Tab 切换「诊断报告 / Agent 轨迹」。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# 直接 `streamlit run uediag/web.py` 时，uediag/ 才是 sys.path[0]，项目根不在里面
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

# 入口第一件事：配置自举（缺 .env 就生成模板），和 cli.py 保持一致
from uediag.types import cfg, ensure_env

ensure_env()

from uediag.report import render_markdown, usage_line  # noqa: E402
from uediag.trace import read_trace  # noqa: E402

UPLOAD_DIR = _ROOT / "runs" / "uploads"

CATEGORY_CN = {
    "crash": "崩溃", "compile": "编译错误", "build": "打包/构建", "cook": "烘焙(Cook)",
    "asset": "资源/导入", "perf": "性能", "network": "网络", "unknown": "未确定",
}
CONFIDENCE_CN = {"high": "🟢 高", "medium": "🟡 中", "low": "🔴 低"}
PHASE_CN = {"perceive": "感知", "plan": "规划", "execute": "执行", "finish": "收尾"}


# ── 落盘上传文件 ────────────────────────────────────────────
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LOG_SUFFIXES = {".log", ".txt"}
# 有些日志名为 .log 但其实是 UTF-16；GBK 是中文 Windows 控制台导出的常见编码
LOG_ENCODINGS = ("utf-8-sig", "utf-16", "gbk", "latin-1")


def classify(uploaded) -> str:
    """判定拖进来的是日志还是截图：先看后缀，后缀不可信时看 MIME。"""
    suffix = Path(uploaded.name).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in LOG_SUFFIXES:
        return "log"
    mime = (getattr(uploaded, "type", "") or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("text/"):
        return "log"
    # 实在认不出来：按图片的魔数猜（PNG/JPEG/GIF/WEBP）
    head = bytes(uploaded.getbuffer())[:12]
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or head.startswith(b"GIF8") \
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    return "log"                                  # 兜底当日志：当成文本试读还有救


def decode_log(raw: bytes) -> tuple[str, str]:
    """日志字节 → 文本。返回 (文本, 实际用的编码)。逐个试，全失败才替换坏字符。"""
    for enc in LOG_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def save_bytes(raw: bytes, name: str, prefix: str) -> str:
    """落盘到 runs/uploads/，返回路径。

    agent.run() 收的是路径（CLI 也是这么传的），所以必须落盘而不是直接传 bytes。
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(name).name                             # 去掉可能的目录部分
    dest = UPLOAD_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{prefix}-{safe}"
    dest.write_bytes(raw)
    return str(dest)


# ── 右栏：trace 时间线 ──────────────────────────────────────
def render_trace(trace_id: str) -> None:
    steps = read_trace(trace_id)
    if not steps:
        st.info("没有轨迹文件。")
        return

    total_ms = sum(s.get("latency_ms") or 0 for s in steps)
    total_cost = sum(s.get("cost_cny") or 0 for s in steps)
    real_steps = [s for s in steps if s.get("phase") != "perceive"]
    st.caption(f"{len(real_steps)} 步 · {total_ms / 1000:.1f} 秒 · {total_cost:.4f} 元")

    for s in steps:
        phase = PHASE_CN.get(s.get("phase"), s.get("phase") or "?")
        action = s.get("action") or "—"
        ok = s.get("ok", True)
        head = f"{'✅' if ok else '⚠️'} [{s.get('idx')}] {phase} · {action}"
        lat = s.get("latency_ms") or 0
        if lat:
            head += f" · {lat} ms"
        with st.expander(head, expanded=(not ok)):
            meta = []
            if s.get("model"):
                meta.append(f"模型 `{s['model']}`")
            if s.get("tokens_in") or s.get("tokens_out"):
                meta.append(f"tokens {s.get('tokens_in', 0)}→{s.get('tokens_out', 0)}")
            if s.get("cost_cny"):
                meta.append(f"{s['cost_cny']:.6f} 元")
            if meta:
                st.caption(" · ".join(meta))
            if s.get("args"):
                st.markdown(f"**参数** `{s['args']}`")
            obs = (s.get("observation") or "").strip()
            if obs:
                st.markdown(obs)


# ── 中栏：报告 ──────────────────────────────────────────────
def render_report(report, docs) -> None:
    conf = CONFIDENCE_CN.get(report.confidence, report.confidence)
    cat = CATEGORY_CN.get(report.category, report.category)

    c1, c2, c3 = st.columns(3)
    c1.metric("分类", cat)
    c2.metric("置信度", conf)
    c3.metric("花费", f"{report.cost_cny:.4f} 元")

    if report.confidence == "low":
        st.warning("置信度低：知识库可能没覆盖这个问题，**别照猜的方案动手**，建议找程序同学确认。")

    st.markdown(render_markdown(report, docs))
    st.caption(usage_line(report))          # 成本/trace 走 caption：markdown 里放 <sub> 不会渲染

    st.download_button(
        "下载报告（Markdown）",
        data=render_markdown(report, docs).encode("utf-8"),
        file_name=f"diagnosis-{report.trace_id or 'report'}.md",
        mime="text/markdown",
        width="stretch",
    )
    with st.expander("原始 JSON（接 CI / 存档用）"):
        st.json(report.to_dict())


# ── 启动即预热：把「第一次检索」的 10 秒挪到打开页面时 ──────────
@st.cache_resource(show_spinner=False)
def warm_up() -> str:
    """加载嵌入模型 + 向量库连接，只在整个进程里做一次。

    必须缓存：Streamlit 每次交互都重跑脚本，不缓存就会每次点按钮都重载 2.1 GB 权重。
    返回一行给人看的状态文字。
    """
    from uediag import kb

    if cfg("EMBED_BACKEND") == "mock":
        return "EMBED_BACKEND=mock，跳过权重加载（离线单测模式）"

    kb.embed_dim()                      # 触发 SentenceTransformer 加载并缓存向量维度
    col = kb.collection()               # 顺手把 Chroma 连接也建好
    return f"嵌入模型已就绪（{cfg('EMBED_MODEL')}）· 知识库 {col.count()} 条"


# ── 页面 ────────────────────────────────────────────────────
st.set_page_config(page_title="UE5 智诊助手 DEMO", page_icon="🛠️", layout="wide")

# 加载态的全屏遮罩样式。两个坑都是实测出来的：
#  1) 别写 `.stApp > * { display:none }` —— 会把 section.main 整块藏掉，遮罩跟着变 0x0。
#     这里只藏 section.main 的直系子元素；遮罩是 position:fixed，照样铺满视口。
#  2) 别用 `background: var(--background-color, #fff)` —— 该变量在深色主题下不解析，会走
#     #fff 白底，而 st.spinner 的文字与图标是白色的（为深色主题准备）→ 白底白字，
#     整页看起来就是「全白」。所以背景、文字、spinner 都显式给色值。
_LOADING_CSS = """
<style>
/* 三重保险，任一条单独失效都不会漏出后面的内容：
   1) 隐藏 section.main 的直系子元素（用 :has() 精确放行遮罩所在的那一层）
   2) 遮罩自身超大 z-index —— 不依赖 DOM 顺序，也不赌内容容器有没有 z-index
   3) body 禁止滚动，避免遮罩是 fixed 而背后内容仍能滚出来 */
section.main[data-testid="stMain"] > div { display: none !important; }
section.main[data-testid="stMain"] > div:has(#uediag-loading) { display: flex !important; }
[data-testid="stSidebar"],
[data-testid="stHeader"],
[data-testid="stToolbar"] { display: none !important; }
body { overflow: hidden !important; }
#uediag-loading {
  position: fixed; inset: 0; z-index: 2147483000;
  display: flex !important; flex-direction: column;
  align-items: center; justify-content: center;
  gap: .6rem; text-align: center;
  background: #cccccc;
  color: #111827;
}
#uediag-loading h2 { margin: 0; font-size: 1.25rem; font-weight: 600; color: #111827; }
#uediag-loading p  { margin: 0; font-size: .9rem; color: #6b7280; max-width: 34rem; }
/* 自己画转圈：st.spinner 会渲染成独立的 element container（是遮罩的**兄弟**而不是子节点），
   所以 #uediag-loading 里的规则够不到它；而它自带近白色文字/图标 → 白底上等于看不见 */
#uediag-loading .spinner {
  width: 42px; height: 42px; border-radius: 50%;
  border: 4px solid #e5e7eb; border-top-color: #ef4444;
  animation: uediag-spin .9s linear infinite;
}
@keyframes uediag-spin { to { transform: rotate(360deg); } }
</style>
"""

if not st.session_state.get("warm_done"):
    # 首次进页面：整屏只留中间一个转圈，把后面的渲染和加载都挡在外面
    st.markdown(_LOADING_CSS, unsafe_allow_html=True)
    box = st.empty()                        # 留着句柄：无论成败，rerun 前都把它清空
    with box.container():
        st.markdown(
            '<div id="uediag-loading">'
            '<div class="spinner"></div>'
            "<h2>正在加载嵌入模型（BGE-M3）</h2>"
            "<p>约 2.1 GB，首次启动需要十几秒；加载完成后只需一次，之后打开页面即刻可用。</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    try:
        # 不用 st.spinner：它渲染在遮罩外面且自带浅色文字，白底上看不见（见上面的样式说明）
        st.session_state.warm_status = warm_up()
    except Exception as e:                  # 权重缺失/损坏 → 回到正常页面并提示，别卡死在加载态
        st.session_state.warm_status = f"加载失败：{type(e).__name__}: {e}"
        st.session_state.warm_failed = True
    st.session_state.warm_done = True
    box.empty()                             # 必须在 rerun 前清掉，否则遮罩会盖住失败提示
    st.rerun()

st.title("🛠️ UE5 智诊助手 DEMO")
st.caption("上传日志（可选截图）→ Agent 自己决定检索什么 → 右边是结论与它每一步的轨迹")

if st.session_state.get("warm_failed"):
    st.error(f"嵌入模型加载失败，检索会不可用：{st.session_state.warm_status}\n\n"
             "先在终端跑 `python -m uediag.fetch_model` 拉权重，然后刷新页面。")
else:
    st.caption("✅ " + st.session_state.warm_status)

if "report" not in st.session_state:
    st.session_state.report = None
    st.session_state.docs = None

# 两栏：左边输入，右边是「报告 / 轨迹」两个 Tab（合并后空间给足）
left, right = st.columns([1, 2.3], gap="large")

# ── 左栏 ────────────────────────────────────────────────────
with left:
    st.subheader("输入")

    # file_uploader 留在表单外：表单内的控件不触发 rerun，选完文件就看不到预览了
    uploads = st.file_uploader(
        "上传日志或者截图",
        type=["log", "txt", "png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=True,
        help="日志认 .log/.txt，截图认图片后缀；会自动按类型分流。也可以只上传其中一种。",
    )

    # 认出来的文件按类型分流，并把判定结果摊给用户看（免得传错了不知道）
    log_files, image_files = [], []
    for f in uploads or []:
        (image_files if classify(f) == "image" else log_files).append(f)

    if log_files or image_files:
        st.caption(f"识别到：日志 {len(log_files)} 个 · 截图 {len(image_files)} 个")
        for f in uploads or []:
            st.caption(("🖼️ " if classify(f) == "image" else "📄 ") + f.name)

    if len(image_files) > 1:
        st.warning(f"一次只能带 1 张截图进诊断，将只用第一张（{image_files[0].name}）。")
    if image_files:
        st.image(image_files[0], caption="待分析截图", width="stretch")

    # 文本 + 提交按钮放进 form：点击时把输入框的当前值**一并**提交。
    # 不用 form 的话，输入框的值要等失焦才提交 → 第一次点击只是失焦、第二次才真正触发诊断。
    #
    # 注意：这里**不能**给提交按钮加 disabled。form 内的控件不触发 rerun，只打字不会产生 rerun，
    # disabled 会一直停在 True，按钮就彻底点不动了（实测死锁）。所以改为点击后服务端校验。
    with st.form("diagnose_form"):
        note = st.text_area(
            "直接描述问题",
            placeholder="例：编译插件报C4096，怎么解决？",
            height=240,
        )
        run_clicked = st.form_submit_button(
            "开始诊断",
            type="primary",
            width="stretch",
        )

    st.divider()
    st.caption(
        "技术栈：\n\n"
        f"文本模型 `{cfg('MODEL_TEXT')}`\n\n"
        f"视觉模型 `{cfg('MODEL_VISION')}`\n\n"
        f"嵌入模型 `{cfg('EMBED_MODEL')}`（{cfg('EMBED_BACKEND')}）\n\n"
        f"向量库 :green[**ChromaDB**]\n\n"
        f"检索 {cfg('RETRIEVER')} · top_k {cfg('TOP_K')} · 最多 {cfg('MAX_STEPS')} 步"
    )
    if not cfg("OPENAI_API_KEY"):
        st.error("`.env` 里没有 OPENAI_API_KEY，先在左栏下方填或直接改 `.env`。")

# ── 触发诊断 ────────────────────────────────────────────────
if run_clicked:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"

    # 日志：多个就按上传顺序拼成一份，末尾各留一行标记原始文件名，方便回溯
    log_path = None
    if log_files:
        chunks = []
        for f in log_files:
            text, enc = decode_log(bytes(f.getbuffer()))
            if len(log_files) > 1:
                chunks.append(f"===== {f.name}（{enc}）=====\n{text}")
            else:
                chunks.append(text)
        log_path = str(UPLOAD_DIR / f"{stamp}-merged.log")
        Path(log_path).write_text("\n\n".join(chunks), encoding="utf-8")

    img_path = None
    if image_files:
        img_path = save_bytes(bytes(image_files[0].getbuffer()), image_files[0].name, "shot")

    if not log_path and not img_path and not note.strip():
        st.warning("至少要给日志、截图或一句描述，否则没有可分析的证据。")
    else:
        try:
            from uediag.agent import run as run_agent
        except ImportError as e:
            st.error(f"`uediag/agent.py` 还没有可用的 run()：{e}")
        else:
            # 权重已在页面打开时预热过，这里通常直接开始跑
            with st.spinner("Agent 正在规划与检索……"):
                try:
                    st.session_state.report = run_agent(
                        log_path=log_path, image_path=img_path, note=note.strip()
                    )
                    st.session_state.docs = getattr(st.session_state.report, "_docs", None)
                except Exception as e:                  # 网络/鉴权/模型报错 → 别让整页白屏
                    st.session_state.report = None
                    st.exception(e)

# ── 右栏：报告 / 轨迹 用 Tab 整合到一处，点标题切换 ──────────────
with right:
    tab_report, tab_trace = st.tabs(["📋 诊断报告", "🔍 Agent 轨迹"])

    with tab_report:
        if st.session_state.report is None:
            st.info("还没有结果。左边拖入日志或截图，点「开始诊断」。")
        else:
            render_report(st.session_state.report, st.session_state.docs)

    with tab_trace:
        st.caption("这是「规划真的发生了」的证据：检索 query 是模型自己写的，不是代码里写死的。")
        if st.session_state.report is None:
            st.info("跑一次诊断后，这里会逐步显示它调了哪些工具、看到了什么。")
        else:
            render_trace(st.session_state.report.trace_id)
