"""报告渲染：同一份 DiagnosisReport，两种呈现（终端 Markdown / JSON）。"""

from __future__ import annotations

import json

CATEGORY_CN = {
    "crash":    "崩溃",
    "compile":  "编译错误",
    "build":    "打包/构建",
    "cook":     "烘焙(Cook)",
    "asset":    "资源/导入",
    "perf":     "性能",
    "network":  "网络",
    "unknown":  "未知",
}
CONFIDENCE_CN = {"high": "高", "medium": "中", "low": "低"}


def render_markdown(report, docs: list | None = None) -> str:
    refs = {d.doc_id: d for d in (docs or [])}
    lines: list[str] = []
    lines.append(f"## 诊断结果：{CATEGORY_CN.get(report.category, report.category)}")
    if report.summary:
        lines.append(f"\n**总结**：\n{report.summary}")
    if report.root_cause:
        lines.append(f"\n**原因**：\n{report.root_cause}")

    if report.fix_steps:
        lines.append("\n**How To Fix** ：\n")
        for i, s in enumerate(report.fix_steps, 1):
            lines.append(f"{i}. {s}")

    if report.escalate_to:
        lines.append(f"\n**上报**：\n{report.escalate_to}")

    if report.evidence_refs:
        lines.append("\n**依据**:\n")
        for r in report.evidence_refs:
            d = refs.get(r)
            if d:
                lines.append(f"- [{r}] {d.title}" + (f" — {d.source_url}" if d.source_url else ""))
            elif docs is None:
                lines.append(f"- [{r}]")
            else:
                lines.append(f"- [{r}] ⚠️ 该引用不在本次检索结果里")
    else:
        lines.append("\n**依据**：\n无 —— 知识库没覆盖这个问题。")

    return "\n".join(lines)


def usage_line(report) -> str:
    """一行摘要（纯文本，无 HTML）。

    **不要**在这里用 `<sub>` 之类的内联 HTML：Streamlit 的 `st.markdown` 默认
    `unsafe_allow_html=False`，会把标签转义成字面文本显示出来（踩过）。
    花费与 trace 属于元信息，由各外壳决定怎么渲染：UI 用 caption，CLI 直接打印。
    """
    return f"花费 {report.cost_cny:.4f} 元 · trace {report.trace_id or '—'}"


def to_json(report, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=indent)
