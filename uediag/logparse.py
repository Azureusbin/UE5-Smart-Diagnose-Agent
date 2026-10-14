"""日志收敛：clean_log()

把任意大小的 UE 日志（几百 KB ~ 几十 MB）收敛成一小段确定性事实（Evidence）：
    1. 抽错误码 / 异常签名
    2. 剔除引擎帧，只留栈顶的「业务帧」
    3. 截取报错附近的上下文窗口，窗口之间用 --- 标记被跳过的区间
    4. 末尾做脱敏

两个设计要点：
- **全文流式扫描**，不 read() 整个文件：内存 O(窗口数)，时间 O(文件)。
  不能只读文件末尾——打包/烘焙失败的报错常常在开头。
- **窗口之间插 ---**：否则模型会误以为上下文连续，脑补因果关系。

正则只覆盖常见格式，**拿真实日志跑一遍再调**（不同 UE 版本、不同平台栈格式有差异）。
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Iterable, Iterator

from uediag.types import Evidence

# ── 正则库（都做成模块级常量，方便对着真实日志一条条调）──────────
TS = re.compile(r"^\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3}\]\[\s*\d+\]\s*")

# 什么算「关键行」：命中就开始一个窗口
KEY = re.compile(
    r"(error:|fatal|ensure|assertion failed|exception|\[callstack\]|unresolved external)",
    re.IGNORECASE,
)

# 错误码：LNK2019 / C2065 / MSB3073……（前面不能是字母数字，排除 0xC0000005 这类地址）
CODE = re.compile(r"(?<![0-9A-Za-z])((?:LNK|MSB|C)\d{3,5})\b")
EXC = re.compile(r"\b(EXCEPTION_[A-Z_]+)\b")
FATAL = re.compile(r"(Fatal error|Ensure condition failed|Assertion failed)", re.IGNORECASE)
# 没有错误码的场景（蓝图/烘焙/打包）只能靠日志标签当抓手
LOGTAG = re.compile(r"\b(Log[A-Za-z]+):\s*(?:Error|Fatal)", re.IGNORECASE)
LOGTAG_NOISE = {"LogWindows", "LogOutputDevice", "LogInit", "LogTemp"}

# 栈帧：UnrealEditor-MyGame.dll!UMyTank::OnFire()  或  MyGame!UMyTank::OnFire(
FRAME = re.compile(r"([A-Za-z0-9_\-\.]+?\.dll|[A-Za-z0-9_]+)!\s*([A-Za-z_~][\w:<>~]*)\s*\(")
BRACKET_PATH = re.compile(r"\[([A-Za-z]:\\[^\]]*)\]")

# 引擎帧的识别特征：路径（首选）与模块名（兜底）
ENGINE_PATH_HINTS = ("\\engine\\", "/engine/", "\\source\\runtime\\", "/source/runtime/")
ENGINE_MODULES = {
    "UnrealEditor-Core", "UnrealEditor-CoreUObject", "UnrealEditor-Engine", "UnrealEditor-Slate",
    "UnrealEditor-RHI", "UnrealEditor-D3D12RHI", "UnrealEditor-RenderCore", "UnrealEditor-Renderer",
    "UnrealEditor-ApplicationCore", "UnrealEditor-InputCore", "UnrealEditor-Projects",
    "UnrealEditor-Kismet", "UnrealEditor-BlueprintGraph", "UnrealEditor-GameplayTasks",
    "UnrealEditor-UMG", "UnrealEditor-EngineSettings", "UnrealEditor-MovieScene",
}

# 脱敏：默认规则 + knowledge/redact.txt（每行 `正则 => 替换`，替换省略则打码）
DEFAULT_REDACT: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    # 注意：re.sub 的替换串里反斜杠要写两遍，否则 \U 会被当成转义
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+"), r"C:\\Users\\<user>"),
]


# ── 公开接口 ─────────────────────────────────────────────────
def clean_log(
    path: str | Path | None = None,
    text: str | None = None,
    *,
    before: int = 3,
    after: int = 12,
    max_windows: int = 40,
    max_codes: int = 8,
) -> Evidence:
    """日志 → Evidence。path 与 text 二选一。"""
    ev = Evidence(source=str(path) if path else "")
    buf: deque[str] = deque(maxlen=before)     # 关键行之前的上下文
    windows: deque[list[str]] = deque(maxlen=max_windows)
    first_window: list[str] | None = None
    cur: list[str] | None = None
    need = 0                                   # 当前窗口还需要往后收几行
    last_key_idx = -10**9
    idx = 0

    for raw in _iter_lines(path, text):
        line = TS.sub("", raw).rstrip()
        if not line:
            continue
        idx += 1
        _absorb_codes(ev, line)
        if ev.top_project_frame is None:
            ev.top_project_frame = _project_frame(line)

        if KEY.search(line):
            if cur is None or idx - last_key_idx > before:
                if cur:
                    windows.append(cur)
                cur = list(buf)                # 新窗口：补上前面 before 行
            cur.append(line)
            need, last_key_idx = after, idx
            if first_window is None:
                first_window = cur
        elif need > 0 and cur is not None:
            cur.append(line)
            need -= 1

        buf.append(line)

    if cur:
        windows.append(cur)

    ev.error_codes = _dedup(ev.error_codes)[:max_codes]
    ev.log_tags = _dedup(ev.log_tags)[:max_codes]
    ev.key_lines = _redact(_flatten(windows, first_window))
    return ev


def iter_windows(ev: Evidence) -> list[list[str]]:
    """把 key_lines 按 --- 切开（UI/调试用）。"""
    out: list[list[str]] = []
    cur: list[str] = []
    for line in ev.key_lines:
        if line.strip() == "---":
            if cur:
                out.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        out.append(cur)
    return out


# ── 内部实现 ─────────────────────────────────────────────────
def _iter_lines(path: str | Path | None, text: str | None) -> Iterator[str]:
    if text is not None:
        yield from text.splitlines()
        return
    if path is None:
        return
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:                         # 流式，不占内存
            yield line


def _absorb_codes(ev: Evidence, line: str) -> None:
    ev.error_codes.extend(CODE.findall(line))
    ev.error_codes.extend(EXC.findall(line))
    ev.error_codes.extend(FATAL.findall(line))
    for tag in LOGTAG.findall(line):
        if tag not in LOGTAG_NOISE:
            ev.log_tags.append(tag)


def _project_frame(line: str) -> str | None:
    """返回这一行里第一个「业务帧」；全是引擎帧则返回 None。"""
    m = FRAME.search(line)
    if not m:
        return None
    module, symbol = m.group(1), m.group(2)
    pm = BRACKET_PATH.search(line)
    source_path = pm.group(1) if pm else None
    if _is_engine(module, source_path):
        return None
    return f"{module}!{symbol}"


def _is_engine(module: str, source_path: str | None) -> bool:
    if source_path:
        low = source_path.lower()
        if any(h in low for h in ENGINE_PATH_HINTS):
            return True
    base = module[:-4] if module.lower().endswith(".dll") else module
    return base in ENGINE_MODULES


def _flatten(windows: deque[list[str]], first_window: list[str] | None) -> list[str]:
    """把窗口拼成一段文本，中间用 --- 标识跳过的区间。"""
    wins = list(windows)
    if first_window is not None and (not wins or wins[0] is not first_window):
        wins.insert(0, first_window)           # 窗口太多被 deque 挤掉时，保住第一个

    out: list[str] = []
    for i, w in enumerate(wins):
        if i > 0:
            out.append("---")
        out.extend(_dedup_consecutive(w))
    return out


def _dedup(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _dedup_consecutive(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for x in items:
        if not out or out[-1] != x:
            out.append(x)
    return out


def _redact(lines: list[str], redact_file: str = "knowledge/redact.txt") -> list[str]:
    rules = list(DEFAULT_REDACT)
    p = Path(redact_file)
    if p.exists():
        for raw in p.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            pattern, _, repl = raw.partition("=>")
            try:
                rules.append((re.compile(pattern.strip()), repl.strip() or "***"))
            except re.error:
                continue
    out = []
    for line in lines:
        for pat, repl in rules:
            line = pat.sub(repl, line)
        out.append(line)
    return out
