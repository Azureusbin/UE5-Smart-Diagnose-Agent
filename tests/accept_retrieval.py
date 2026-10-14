"""M1 验收：检索层能不能把「现象」对到正确的 case。

    python tests/accept_retrieval.py

两类 query 都要过：
- **错误码类**（`LNK2019` / `EXCEPTION_ACCESS_VIOLATION`）——符号精确匹配
- **口语化类**（「开火就崩」「一进游戏就闪退」）——语义匹配，用户真会这么问

全过退出码 0，有 MISS 退出码 1（方便以后接 CI）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uediag.kb import search_kb          # noqa: E402
from uediag.types import ensure_env      # noqa: E402

# (query, 期望命中的 case, 类别)
CASES: list[tuple[str, str, str]] = [
    ("LNK2019 unresolved external symbol", "UE-ERR-0001", "错误码"),
    ("error C2065 undeclared identifier", "UE-ERR-0005", "错误码"),
    ("EXCEPTION_ACCESS_VIOLATION", "UE-ERR-0002", "错误码"),
    ("Ensure condition failed", "UE-ERR-0004", "关键字"),
    ("开火就崩", "UE-ERR-0002", "口语化"),
    ("一进游戏就闪退", "UE-ERR-0002", "口语化"),
    ("蓝图编译过不去", "UE-ERR-0003", "口语化"),
    ("打包的时候链接报错", "UE-ERR-0001", "口语化"),
]


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ensure_env()

    print(f"{'query':<38} {'期望':<13} {'Top1':<13} {'Top3':<6} 判定   类别")
    print("-" * 92)
    top1_ok = 0
    top3_ok = 0
    for query, want, kind in CASES:
        ids = [d.doc_id for d in search_kb(query, top_k=3)]
        got = ids[0] if ids else "-"
        hit1, hit3 = got == want, want in ids
        top1_ok += hit1
        top3_ok += hit3
        flag = "OK" if hit1 else ("~" if hit3 else "MISS")
        print(f"{query:<38} {want:<13} {got:<13} {str(hit3):<6} {flag:<6} {kind}")

    n = len(CASES)
    print("-" * 92)
    print(f"Top-1 命中 {top1_ok}/{n}    Top-3 命中 {top3_ok}/{n}")
    if top1_ok == n:
        print("M1 验收通过：错误码类与口语化类都能命中")
        return 0
    print("M1 未通过。排查顺序：① kb rebuild 跑了没 ② embed_text 是否含错误码/症状 "
          "③ 该 case 的 keywords 是不是缺了用户会说的词")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
