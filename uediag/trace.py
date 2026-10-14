"""轨迹：把 Agent 每一步摊开——这是「规划真的发生了」的唯一证据。

agent.py 里这样用：

    from uediag.trace import TraceRecorder
    tr = TraceRecorder()                       # 或 TraceRecorder(trace_id)
    tr.perceive(evidence)                      # 轮 0：确定性抽取
    tr.step(phase="plan", action="search_kb", args={"query": q}, model=MODEL_TEXT,
            observation="命中 3 条", latency_ms=2140, tokens_in=1832, tokens_out=96, cost_cny=0.0019)
    report.trace_id = tr.trace_id              # 交给报告，UI 靠它找文件
    tr.finish(report)

落盘：{TRACE_DIR}/{trace_id}.jsonl，一行一个 JSON。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from uediag.types import cfg


def new_trace_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def trace_path(trace_id: str) -> Path:
    return Path(cfg("TRACE_DIR")) / f"{trace_id}.jsonl"


class TraceRecorder:
    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or new_trace_id()
        self.path = trace_path(self.trace_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self._t0 = time.perf_counter()

    # ── 记录 ────────────────────────────────────────────
    def step(
        self,
        *,
        phase: str,
        action: str | None = None,
        args: dict | None = None,
        observation: str | None = None,
        ok: bool = True,
        model: str = "",
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_cny: float = 0.0,
    ) -> dict:
        entry = {
            "idx": len(self.steps),
            "ts": round(time.perf_counter() - self._t0, 3),
            "phase": phase,
            "action": action,
            "args": args or {},
            "observation": _trim(observation),
            "ok": ok,
            "model": model,
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_cny": round(cost_cny, 6),
        }
        self.steps.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def perceive(self, evidence) -> dict:
        """轮 0：规则抽取，不花 LLM 钱。"""
        return self.step(
            phase="perceive",
            action="clean_log",
            observation=(f"错误码={evidence.error_codes} 标签={evidence.log_tags} "
                         f"栈顶业务帧={evidence.top_project_frame}"),
            model="",
        )

    def finish(self, report=None) -> None:
        """收尾。**注意不要把报告的总花费记进来**——那是各步之和，记在这里会重复计费。"""
        self.step(
            phase="finish",
            action="finish",
            observation=(f"{report.category} / {report.confidence} / 引用 {report.evidence_refs}"
                         if report else "结束"),
        )

    # ── 汇总 ────────────────────────────────────────────
    def summary(self) -> str:
        steps = [s for s in self.steps if s["phase"] != "perceive"]
        cost = sum(s["cost_cny"] for s in self.steps)
        wall = self.steps[-1]["ts"] if self.steps else 0
        return f"{len(steps)} 步 · {wall:.1f} 秒 · {cost:.4f} 元 · trace={self.trace_id}"


def read_trace(trace_id: str) -> list[dict]:
    p = trace_path(trace_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def print_trace(trace_id_or_steps: str | list[dict]) -> None:
    steps = read_trace(trace_id_or_steps) if isinstance(trace_id_or_steps, str) else trace_id_or_steps
    if not steps:
        print("（没有轨迹）")
        return
    for s in steps:
        head = f"[{s['idx']}] {s['phase']:<8} {s['latency_ms']:>6}ms"
        tag = f" ({s['model'].split('-')[-1]})" if s.get("model") else ""
        if s.get("action") and s["action"] != "clean_log":
            print(f"{head}  → {s['action']}({_compact(s.get('args'))}){tag}")
        if s.get("observation"):
            print(f"{'':<14}← {s['observation']}")
    total_cost = sum(s["cost_cny"] for s in steps)
    total_ms = sum(s["latency_ms"] for s in steps)
    print("─" * 64)
    print(f"合计 {len([s for s in steps if s['phase'] != 'perceive'])} 步 · "
          f"{total_ms / 1000:.1f} 秒 · {total_cost:.4f} 元")


# ── 工具函数 ─────────────────────────────────────────────
def _trim(text: str | None, limit: int | None = None) -> str:
    if not text:
        return ""
    limit = limit or int(cfg("MAX_OBSERVATION_CHARS"))
    text = text if len(text) <= limit else text[:limit] + "…"
    return text


def _compact(args: Any, limit: int = 90) -> str:
    if not isinstance(args, dict) or not args:
        return ""
    parts = [f"{k}={v!r}" for k, v in args.items()]
    s = ", ".join(parts)
    return s if len(s) <= limit else s[:limit] + "…"
