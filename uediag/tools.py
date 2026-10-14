import json
from uediag import llm
from uediag.kb import search_kb
from uediag.types import cfg_int, RetrievedDoc

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function":{
            "name": "search_kb",
            "description": (
                "在 UE 排障知识库里检索同类案例。**不确定根因时必须先调用它，不要凭记忆回答。**"
                "query 里要保留错误码原文（例如 LNK2019、EXCEPTION_ACCESS_VIOLATION），不要改写或翻译它们。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索词：错误码 + 模块名 + 现象，中英文都可以"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回条数，默认 3", "minimum": 1, "maximum": 10
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function":{
            "name": "read_screenshot",
            "description": (
                "查看用户提供的截图。会在内部调用视觉模型做信息抽取，返回纯文本。"
                "当日志证据不足、或用户说「看截图」时必须调用。"
                "输入必须是上面给出的可用截图路径，不要自己编路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "image_ref": { "type": "string", "description": "可用截图路径（原文件传，不要改动）" },
                    "question": { "type": "string", "description": "你想在图里确认什么，例如「截图里的错误码」" },
                },
                "required": ["image_ref", "question"],
            },
        },
    },
    {
        "type": "function",
        "function":{
            "name": "finish",
            "description": (
                "诊断完成，提交结构化结论。**证据不足时也要调用它**——把 confidence 填 low 并在 summary 里"
                "说明「知识库未覆盖」，不要编造修复步骤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category":         { "type": "string", "enum": ["crash", "compile", "build", "cook", "asset", "perf", "unknown"] },
                    "confidence":       { "type": "string", "enum": ["high", "medium", "low"] },
                    "summary":          { "type": "string", "description": "一句话结论，说给非技术同学听" },
                    "root_cause":       { "type": "string", "description": "根因；不确定就写「暂无法确定」" },
                    "fix_steps":        { "type": "array", "items": {"type": "string"}, "description": "按顺序的修复步骤，给到具体菜单路径" },
                    "escalate_to":      {"type": "string", "description": "该找谁：程序组 / TA / 构建机"},
                    "evidence_refs":    {"type": "array", "items": {"type": "string"}, "description": "依据的 case 编号，如 UE-ERR-0002; 只能用检索结果里出现过的"},
                },
            },
        },
    },
]

# 收尾工具
FINISH_SCHEMA = TOOL_SCHEMAS[-1]


def dispatch(name: str, args: dict) -> tuple[str, list[RetrievedDoc]]:
    try:
        if name == "search_kb":
            return _search_kb(args)
        if name == "read_screenshot":
            return _read_screenshot(args)
        
        return f"未知工具 {name}，可用工具：search_kb / read_screenshot / finish。", []
    
    except Exception as e:
        return f"工具 {name} 执行失败：{type(e).__name__}: {e}。请换个方式重试，或直接 finish。", []


def _search_kb(args: dict) -> tuple[str, list[RetrievedDoc]]:
    query = str(args.get("query") or "").strip()

    if not query:
        return "query 不能为空。请把错误码和现象一起写进 query。", []

    k = int(args.get("top_k") or cfg_int("TOP_K"))
    docs = search_kb(query, top_k=k)
    if not docs:
        return (f"知识库没有任何命中（query={query!r}）。"
                f"可以换关键词再试一次，或直接 finish 并在 summary 里说明知识库未覆盖。", [])

    lines = [f"命中结果：{len(docs)} 条"]
    for i, d in enumerate(docs, 1):
        lines.append(f"\n{i}. [{d.doc_id}] {d.title}（score={d.score:.4f}）\n{d.body}")
    lines.append("\n提示：引用时只能写上面出现过的编号；需要更多线索可以换关键词再查一次。")
    return "\n".join(lines), docs

def _read_screenshot(args: dict) -> tuple[str, list[RetrievedDoc]]:
    ref = str(args.get("image_ref") or "").strip()
    question = str(args.get("question") or "这张图里的错误或警告是什么？").strip()
    text = llm.describe_image(ref, question)
    if not text:
        return f"截图 {ref} 没有读到内容，可能是图片损坏。可以跳过截图，用日志继续诊断。", []
    return f"截图信息（来自视觉模型，仅客观抽取，不含结论）：\n{text}", []

