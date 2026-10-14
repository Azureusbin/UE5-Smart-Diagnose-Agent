"""从魔搭（ModelScope）拉取 BGE-M3 权重到本地目录。

从魔搭（ModelScope）拉取，BAAI 官方也在上面发布，国内直连无需镜像。

下载完的目录可以直接被 SentenceTransformer 加载（离线），把 .env 里的
`EMBED_MODEL` 指过去即可：`EMBED_MODEL=./models/bge-m3`

用法：
    python -m uediag.fetch_model                    # 默认下到 models/bge-m3
    python -m uediag.fetch_model --dir D:\\models\\bge-m3
    python -m uediag.fetch_model --list             # 只看文件清单，不下载
    python -m uediag.fetch_model --repo BAAI/bge-m3

特性：断点续传（Range）、已完成文件跳过、进度与速度实时打印。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API_LIST = "https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Revision={rev}&Recursive=true"
API_FILE = "https://www.modelscope.cn/api/v1/models/{repo}/repo?Revision={rev}&FilePath={path}"

# sentence-transformers 加载所需（其余如 onnx/、imgs/、colbert/sparse 头都不下）
WANTED_FILES = {
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "pytorch_model.bin",
    "model.safetensors",
    "1_Pooling/config.json",
}
SKIP_PREFIX = ("onnx/", "imgs/", ".")


def list_files(repo: str, rev: str) -> list[tuple[str, int]]:
    url = API_LIST.format(repo=repo, rev=rev)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for f in data["Data"]["Files"]:
        path, size = f.get("Path", ""), int(f.get("Size") or 0)
        if not path or size == 0 or path.startswith(SKIP_PREFIX):
            continue
        if path not in WANTED_FILES:
            continue
        out.append((path, size))
    return sorted(out, key=lambda x: x[0])


def download(repo: str, rev: str, rel: str, size: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if dest.exists() and dest.stat().st_size == size:
        print(f"  [跳过] {rel} 已完整（{_mb(size)}）")
        return
    if have >= size:
        part.replace(dest)
        print(f"  [完成] {rel}（{_mb(size)}）")
        return

    url = API_FILE.format(repo=repo, rev=rev, path=urllib.parse.quote(rel))
    req = urllib.request.Request(url)
    if have:
        req.add_header("Range", f"bytes={have}-")
        print(f"  [续传] {rel} 从 {_mb(have)} 继续 / 共 {_mb(size)}")
    else:
        print(f"  [下载] {rel}  共 {_mb(size)}")

    t0, done, last = time.time(), have, 0.0
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "ab") as f:
        while True:
            chunk = r.read(1 << 20)               # 1 MB
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last > 5 or done >= size:     # 每 5 秒报一次
                last = now
                speed = (done - have) / max(now - t0, 1e-6) / (1 << 20)
                pct = done * 100 / size if size else 0
                print(f"    {_mb(done)}/{_mb(size)}  {pct:5.1f}%  {speed:5.1f} MB/s", flush=True)
    part.replace(dest)
    print(f"  [完成] {rel}")


def _mb(n: int) -> str:
    return f"{n / (1 << 20):.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description="从魔搭拉取 BGE-M3 权重")
    ap.add_argument("--repo", default="BAAI/bge-m3")
    ap.add_argument("--rev", default="master")
    ap.add_argument("--dir", default="models/bge-m3")
    ap.add_argument("--list", action="store_true", help="只列文件，不下载")
    a = ap.parse_args()

    # Windows 控制台乱码保护
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"[取权重] {a.repo} @ {a.rev} → {a.dir}")
    files = list_files(a.repo, a.rev)
    total = sum(s for _, s in files)
    print(f"[取权重] 需要 {len(files)} 个文件，合计 {_mb(total)}")
    if a.list:
        for path, size in files:
            print(f"  {path:<42} {_mb(size)}")
        return 0

    dest = Path(a.dir)
    t0 = time.time()
    for path, size in files:
        download(a.repo, a.rev, path, size, dest / path)
    print(f"\n[取权重] 全部完成，用时 {time.time() - t0:.0f} 秒 → {dest.resolve()}")
    print(f"[取权重] 把 .env 里的 EMBED_MODEL 改成：{dest.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
