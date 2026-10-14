"""报告渲染：同一份 DiagnosisReport，两种呈现（终端 Markdown / JSON）。"""

from __future__ import annotations

import json

CATEGORY_CN = {
    "crash": "崩溃",
    "compile": "编译错误",
    "build": "打包/构建",
    "cook": "烘焙(Cook)",
    "asset": "资源/导入",
    "perf": "性能",
    "network": "网络",
    "unknown": "未确定",
}
CONFIDENCE_CN = {"high": "高", "medium": "中", "low": "低"}


def render_markdown(report, docs: list | None = None) -> str:
    refs = {d.doc_id: d for d in (docs or [])}
    lines: list[str] = []
    lines.append(f"## 诊断结果：{CATEGORY_CN.get(report.category, report.category)}"
                 f"（置信度 {CONFIDENCE_CN.get(report.confidence, report.confidence)}）")
    if report.summary:
        lines.append(f"\n**一句话**：{report.summary}")
    if report.root_cause:
        lines.append(f"\n**根因**：{report.root_cause}")

    if report.fix_steps:
        lines.append("\n**怎么修**")
        for i, s in enumerate(report.fix_steps, 1):
            lines.append(f"{i}. {s}")

    if report.escalate_to:
        lines.append(f"\n**搞不定找谁**：{report.escalate_to}")

    if report.evidence_refs:
        lines.append("\n**依据**")
        for r in report.evidence_refs:
            d = refs.get(r)
            if d:
                lines.append(f"- [{r}] {d.title}" + (f" — {d.source_url}" if d.source_url else ""))
            elif docs is None:
                lines.append(f"- [{r}]")
            else:
                lines.append(f"- [{r}] ⚠️ 该引用不在本次检索结果里")
    else:
        lines.append("\n**依据**：无 —— 知识库没覆盖这个问题，别照猜的方案动手，建议找程序确认。")

    lines.append(f"\n<sub>花费 {report.cost_cny:.4f} 元 · trace {report.trace_id or '—'}</sub>")
    return "\n".join(lines)


def to_json(report, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=indent)
