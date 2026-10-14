"""数据契约 + 配置引导。

这个模块装三类东西：
1. DEFAULTS / ensure_env() / cfg()：配置（.env 自动生成，代码里有默认值）
2. Evidence / RetrievedDoc / DiagnosisReport：§3 数据契约
3. load_prompt()：读 uediag/prompts/ 下的外置提示词

改参数优先改 .env；DEFAULTS 只是兜底。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 默认值：.env 覆盖它们，代码永远是兜底 ──────────────────────
DEFAULTS = {
    "OPENAI_API_KEY": "",
    "OPENAI_API_URL": "https://api.deepseek.com",
    "MODEL_TEXT": "deepseek-v4-flash",
    "MODEL_VISION": "deepseek-v4-flash-vision-exp",
    # 思考模式：enabled | disabled。默认关闭，原因见 llm.chat 的注释
    # （开思考模式后不支持指定函数的 tool_choice，且必须回传 reasoning_content）
    "THINKING": "disabled",
    "REASONING_EFFORT": "high",       # 仅 THINKING=enabled 时生效：low | high | max
    "MAX_STEPS": "6",
    "MAX_OBSERVATION_CHARS": "1200",
    "TOP_K": "3",
    "RRF_K": "60",
    "RETRIEVER": "hybrid",            # hybrid | vector
    "CHROMA_PATH": "./.chroma",
    "KNOWLEDGE_DIR": "./knowledge/ue_errors",
    "EMBED_BACKEND": "local",         # local | mock
    # 权重用 scripts/fetch_model.py 从魔搭下到本地目录，这里指向本地路径 → 离线加载
    "EMBED_MODEL": "./models/bge-m3",
    "VISION_DETAIL": "original",      # 报错截图文字密集，别用 low
    "TRACE_DIR": "./runs",
    "PRINT_TRACE": "false",
}

_ENV_PATH = os.environ.get("UEDIAG_ENV", ".env")


def ensure_env(path: str | None = None) -> str:
    """首次运行生成 .env；已存在则原样保留（绝不覆盖密钥）。返回实际使用的路径。"""
    path = path or _ENV_PATH
    if not os.path.exists(path):
        header = (
            "# 本文件由程序自动生成（uediag/types.py: ensure_env）\n"
            "# 唯一必填：OPENAI_API_KEY\n"
            "# 其余项都有代码内置默认值，改哪条直接改值即可\n\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(f"{k}={v}" for k, v in DEFAULTS.items()) + "\n")
        print(f"[配置] 已生成 {path}，请填入 OPENAI_API_KEY 后重新运行")
    load_dotenv(path)                     # 已存在的环境变量不会被覆盖
    return path


def cfg(key: str) -> str:
    """取配置：环境变量优先，其次 DEFAULTS。"""
    val = os.environ.get(key)
    if val is None or val == "":
        return DEFAULTS[key]
    return val


def cfg_int(key: str) -> int:
    return int(cfg(key))


def cfg_bool(key: str) -> bool:
    return cfg(key).strip().lower() in {"1", "true", "yes", "on"}


def require_api_key() -> str:
    """只有真要调模型的路径才需要它——kb 检索不需要。"""
    key = cfg("OPENAI_API_KEY")
    if not key or key.startswith("sk-你的"):
        raise SystemExit("请在 .env 里填入 OPENAI_API_KEY")
    return key


def load_prompt(name: str) -> str:
    """读 uediag/prompts/<name>.md（不用带后缀）。"""
    path = Path(__file__).resolve().parent / "prompts" / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


# ── §3 数据契约 ───────────────────────────────────────────────
@dataclass
class Evidence:
    """clean_log() 的产物：把日志收敛成一小段确定性事实。"""

    error_codes: list[str] = field(default_factory=list)
    log_tags: list[str] = field(default_factory=list)   # LogBlueprint / LogCook …（没有错误码时的抓手）
    top_project_frame: str | None = None
    key_lines: list[str] = field(default_factory=list)
    source: str = ""                                  # 原始日志路径（报告里回显）

    def render(self) -> str:
        """给模型看的那段文本。"""
        parts = []
        if self.error_codes:
            parts.append("错误码/异常: " + ", ".join(self.error_codes))
        if self.log_tags:
            parts.append("日志标签: " + ", ".join(self.log_tags))
        if self.top_project_frame:
            parts.append("栈顶业务帧: " + self.top_project_frame)
        if self.key_lines:
            parts.append("关键日志:\n" + "\n".join(self.key_lines))
        return "\n".join(parts) or "（未抽取到结构化证据）"


@dataclass
class RetrievedDoc:
    """一次检索命中。body 是全文，直接进上下文。"""

    doc_id: str
    title: str
    score: float
    body: str
    path: str
    source_url: str | None = None
    error_codes: list[str] = field(default_factory=list)

    def brief(self) -> str:
        return f"[{self.doc_id}] {self.title} (score={self.score:.4f})\n{self.body}"


@dataclass
class DiagnosisReport:
    """finish 工具的参数 = 最终产出。UI 只读这些字段。"""

    category: str = "unknown"          # crash/compile/build/cook/asset/perf/unknown
    confidence: str = "low"            # high/medium/low
    summary: str = ""
    root_cause: str = ""
    fix_steps: list[str] = field(default_factory=list)
    escalate_to: str | None = None
    evidence_refs: list[str] = field(default_factory=list)   # 必须 ⊆ 本次检索集合
    cost_cny: float = 0.0
    trace_id: str = ""                 # UI 靠它找 {TRACE_DIR}/{trace_id}.jsonl

    @classmethod
    def from_tool_args(cls, args: dict[str, Any], trace_id: str = "") -> "DiagnosisReport":
        """从 finish 的参数构造。模型不一定给全字段 → 一律给安全默认值。"""
        args = args or {}
        return cls(
            category=str(args.get("category") or "unknown"),
            confidence=str(args.get("confidence") or "low"),
            summary=str(args.get("summary") or ""),
            root_cause=str(args.get("root_cause") or ""),
            fix_steps=[str(x) for x in (args.get("fix_steps") or [])],
            escalate_to=args.get("escalate_to"),
            evidence_refs=[str(x) for x in (args.get("evidence_refs") or [])],
            trace_id=trace_id,
        )

    def to_dict(self) -> dict:
        return asdict(self)
