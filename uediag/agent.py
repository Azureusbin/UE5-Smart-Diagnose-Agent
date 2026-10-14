from __future__ import annotations

from uediag import llm, tools
from uediag.logparse import clean_log
from uediag.trace import TraceRecorder
from uediag.types import DiagnosisReport, Evidence, RetrievedDoc, cfg, cfg_int, ensure_env

SYSTEM_PROMPT = """你是 UE5 项目排障助手，服务对象是策划/美术/QA 和技术新人。

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
    ensure_env()

    # step 0 : 规则抽取
    evidence = clean_log(log_path) if log_path else Evidence()
    tr.perceive(evidence)

    # step 1 : 组装User消息，只给「证据 + 可用截图路径」，图片本身不进上下文
    # 看不看图由模型决定（它自己调 read_screenshot 工具），所以这里只报路径、不预先抽图
    parts = []
    if note:
        parts.append(f"用户描述：{note}")
    parts.append(evidence.render())
    if image_path:
        parts.append(f"可用截图：{image_path}（需要看图时调用 read_screenshot，image_ref 原样填这个路径）")

    messages: list[dict] = [
        { "role": "system", "content": SYSTEM_PROMPT },
        { "role": "user", "content": "\n\n".join(parts) },
    ]

    retrieved: dict[str, RetrievedDoc] = {}
    report: DiagnosisReport | None = None
    seen_calls: set[tuple] = set()          # 防重复：同一 (工具, 参数) 只执行一次

    # 循环
    max_step = cfg_int("MAX_STEPS")
    for _ in range(max_step):
        before = llm.usage()
        with llm.Timer() as t:
            msg = llm.chat(messages, tools=tools.TOOL_SCHEMAS)
        after = llm.usage()

        # assistant 消息必须原样回传（含 tool_calls），否则下一轮的 tool 消息无法配对
        messages.append(llm.as_message_dict(msg))

        tr.step(phase="plan", action=(msg.tool_calls[0].function.name if msg.tool_calls else None),
                observation=(msg.content or "")[:200], model=cfg("MODEL_TEXT"), latency_ms=t.ms,
                tokens_in=after["in"] - before["in"], tokens_out=after["out"] - before["out"],
                cost_cny=after["cost"] - before["cost"])

        # 没有可用的工具则让 llm 调用finish
        if not msg.tool_calls:
            messages.append({"role": "user", "content": "请调用 finish 输出结构化结论。"})
            continue

        for call in msg.tool_calls:
            name = call.function.name
            args = llm.tool_args(call)
            if name == "finish":
                # 必须走 from_tool_args：直接把 args 传成第二个位置参数会落到 confidence 上
                # （陷阱：DiagnosisReport 的第一个位置参数是 category，不是工具名）
                if not args:
                    messages.append({"role": "user", "content": "finish 需要参数，请重新调用 finish。"})
                    continue
                report = DiagnosisReport.from_tool_args(args, tr.trace_id)
                break
            key = (name, tuple(sorted((k, str(v)) for k, v in args.items())))
            if key in seen_calls:
                obs = (f"工具 {name} 的这组参数刚刚已经执行过，结果没有变化。"
                       "请换一组参数 / 关键词重试，或直接调用 finish 收尾。")
            else:
                seen_calls.add(key)
                obs, docs = tools.dispatch(name, args)
                retrieved.update({d.doc_id: d for d in docs})
            messages.append(llm.tool_reply(call.id, obs))
            tr.step(phase="execute", action=name, observation=obs, model=cfg("MODEL_TEXT"))

        if report:
            break

    else:
        messages.append({ "role": "user", "content": "超出预算，请基于现有证据调用 finish。" })


    if report is None:
        msg = llm.chat(messages, tools=[tools.FINISH_SCHEMA], tool_choice={"type": "function", "function": {"name": "finish"}})
        args = llm.tool_args(msg.tool_calls[0] if msg.tool_calls else {})
        report = DiagnosisReport.from_tool_args(args, tr.trace_id)


    report = validate_refs(report, retrieved)
    report.trace_id = tr.trace_id
    report.cost_cny = llm.usage()["cost"]
    report._docs = list(retrieved.values())
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
        note = "***以上结论仅供参考，建议找相关负责人确认。***"
        report.summary = (report.summary + "  \n" + note).strip()
    return report