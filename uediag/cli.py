"""命令行入口：`python -m uediag <子命令>`

这里**只有**「解析参数 → 调函数 → 打印结果」，任何业务判断都不该出现在这个文件，
因为 Streamlit UI 是同一个角色的另一个外壳，要复用同样的函数。

    python -m uediag kb rebuild [--full]     知识库 → BGE-M3 → Chroma 入库（幂等）
    python -m uediag kb check                一致性自查（文件数 vs 向量库文档数）
    python -m uediag kb search "LNK2019"     只跑检索：不调 LLM、不花钱
    python -m uediag log show crash.log      只跑 clean_log：看日志被收敛成什么样
    python -m uediag diagnose --log crash.log [--image shot.png] [--note "..."] [--print-trace]
"""

from __future__ import annotations

import argparse
import sys

from uediag.types import cfg_bool, cfg_int, ensure_env


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，中文和符号会因此报错/乱码 → 统一按 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ensure_env()                                    # 第一件事：配置自举（会在缺失时生成 .env）

    p = argparse.ArgumentParser(prog="uediag", description="UE5 智诊助手")
    sub = p.add_subparsers(dest="cmd", required=True)

    # kb ...
    kb = sub.add_parser("kb", help="知识库：入库 / 自查 / 检索").add_subparsers(dest="kbcmd", required=True)
    kb_rebuild = kb.add_parser("rebuild", help="入库（幂等）")
    kb_rebuild.add_argument("--full", action="store_true", help="全量重建（忽略 hash 缓存）")
    kb.add_parser("check", help="一致性自查")
    kb_search = kb.add_parser("search", help="只跑检索，不调 LLM")
    kb_search.add_argument("query")
    kb_search.add_argument("--top-k", type=int, default=None)

    # log show ...
    log = sub.add_parser("log", help="日志相关").add_subparsers(dest="logcmd", required=True)
    log_show = log.add_parser("show", help="只跑 clean_log，看收敛结果")
    log_show.add_argument("path")

    # diagnose ...
    d = sub.add_parser("diagnose", help="完整链路：clean_log → Agent 循环 → 报告")
    d.add_argument("--log", help="日志文件路径")
    d.add_argument("--image", help="截图路径")
    d.add_argument("--note", default="", help="用户一句话描述")
    d.add_argument("--print-trace", action="store_true", help="打印轨迹时间线")
    d.add_argument("--json", action="store_true", help="以 JSON 输出报告")

    a = p.parse_args(argv)

    if a.cmd == "kb":
        from uediag import kb

        if a.kbcmd == "rebuild":
            print(kb.rebuild(full=a.full))
        elif a.kbcmd == "check":
            print(kb.stats())
        else:
            docs = kb.search_kb(a.query, top_k=a.top_k or cfg_int("TOP_K"))
            if not docs:
                print("没有命中。知识库可能是空的 → 先跑 python -m uediag kb rebuild")
            for i, doc in enumerate(docs, 1):
                print(f"\n{i}. [{doc.doc_id}] {doc.title}  score={doc.score:.4f}")
                print(f"   {doc.path}" + (f"  {doc.source_url}" if doc.source_url else ""))
                print("   " + doc.body.strip().replace("\n", "\n   ")[:600])
        return 0

    if a.cmd == "log":
        from uediag.logparse import clean_log

        ev = clean_log(a.path)
        print(f"错误码/异常: {ev.error_codes}")
        print(f"日志标签: {ev.log_tags}")
        print(f"栈顶业务帧: {ev.top_project_frame}")
        print(f"关键窗口: {len(ev.key_lines)} 行")
        print("-" * 64)
        print("\n".join(ev.key_lines))
        return 0

    # diagnose：调你写的 agent.run()
    try:
        from uediag.agent import run                     # type: ignore
    except ImportError:
        print("[待实现] uediag/agent.py 还没有 run()。\n"
              "  这是你要亲手写的部分：\n"
              "    tools.py —— 3 个工具 + schema + dispatch(name, args) -> (文本, docs)\n"
              "    agent.py —— run(log_path, image_path, note) -> DiagnosisReport（记得填 trace_id）\n"
              "  在这之前，可以先用下面两个子命令验证通用件：\n"
              "    python -m uediag kb search \"LNK2019\"\n"
              "    python -m uediag log show data/samples/crash_demo.log")
        return 2

    from uediag.report import render_markdown, to_json, usage_line
    from uediag.trace import print_trace, read_trace

    report = run(log_path=a.log, image_path=a.image, note=a.note)
    docs = getattr(report, "_docs", None)
    if a.json:
        print(to_json(report))
    else:
        print(render_markdown(report, docs))
        print()                                          # 成本/trace 是元信息，恒打印
        print(usage_line(report))
        if a.print_trace or cfg_bool("PRINT_TRACE"):
            print()
            print_trace(read_trace(report.trace_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
