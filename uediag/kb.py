"""知识库：加载 case → BGE-M3 编码 → Chroma 入库 / 检索（双轨：稠密 + BM25，RRF 融合）。

对外只有四个函数：
    load_cases()                  读 knowledge/ue_errors/*.md
    rebuild(full=False)           入库（幂等：内容 hash 没变就跳过编码）
    search_kb(query, top_k)       检索（对外唯一入口）
    stats()                       一致性自查

依赖：chromadb + sentence-transformers（EMBED_BACKEND=mock 时不需要模型，用于离线单测）。
"""

from __future__ import annotations

import hashlib
import math
import re
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uediag.types import RetrievedDoc, cfg, cfg_int

COLLECTION = "ue_errors"


# ── case 加载 ────────────────────────────────────────────────
@dataclass
class Case:
    id: str
    title: str
    body: str
    path: str
    category: str = "unknown"
    keywords: list[str] = field(default_factory=list)
    error_codes: list[str] = field(default_factory=list)
    source_url: str | None = None
    symptom: str = ""
    content_hash: str = ""

    # 稠密轨喂什么文本：标题 + 关键词 + 错误码 + 症状（不是全文）
    @property
    def embed_text(self) -> str:
        return "\n".join(
            x for x in [self.title, " ".join(self.keywords), " ".join(self.error_codes), self.symptom] if x
        )

    # 稀疏轨打分文本：符号都在正文里，所以要带全文
    @property
    def bm25_text(self) -> str:
        return "\n".join([self.title, " ".join(self.keywords), " ".join(self.error_codes), self.body])


def load_cases(directory: str | None = None) -> list[Case]:
    directory = directory or cfg("KNOWLEDGE_DIR")
    paths = sorted(Path(directory).glob("*.md"))
    cases: list[Case] = []
    for p in paths:
        if p.name.startswith("_"):
            continue
        text = p.read_text(encoding="utf-8")
        meta, body = _split_front_matter(text)
        cid = str(meta.get("id") or p.stem)
        cases.append(
            Case(
                id=cid,
                title=str(meta.get("title") or cid),
                body=body.strip(),
                path=str(p),
                category=str(meta.get("category") or "unknown"),
                keywords=_as_list(meta.get("keywords")),
                error_codes=_as_list(meta.get("error_codes")),
                source_url=(str(meta["source_url"]) if meta.get("source_url") else None),
                symptom=_section(body, "症状") or _first_paragraph(body),
                content_hash=hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
            )
        )
    return cases


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.lstrip().startswith("---"):
        return {}, text
    stripped = text.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_raw = stripped[3:end]
    body = stripped[end + 4 :]
    return _parse_yaml_lite(fm_raw), body


def _parse_yaml_lite(raw: str) -> dict[str, Any]:
    """只支持 `key: value` 与 `key: [a, b, c]`，够用就行，不引 yaml 库。"""
    out: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [x.strip().strip("'\"") for x in re.split(r"[,，]", s) if x.strip()]


def _section(body: str, name: str) -> str:
    m = re.search(rf"^##\s*{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return " ".join(m.group(1).split())[:200] if m else ""


def _first_paragraph(body: str) -> str:
    for para in body.split("\n\n"):
        para = " ".join(para.split())
        if para and not para.startswith("#"):
            return para[:200]
    return ""


# ── 编码器 ───────────────────────────────────────────────────
_st_model = None


def encode(texts: list[str], kind: str = "doc") -> list[list[float]]:
    """文本 → 向量。EMBED_BACKEND=mock 时用确定性的哈希伪向量（离线单测用）。"""
    texts = list(texts)
    if cfg("EMBED_BACKEND") == "mock":
        return [_mock_vector(t) for t in texts]

    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer  # 延迟导入：--help 不用等 torch

        ref = cfg("EMBED_MODEL")
        hint = ("本地权重，离线加载" if Path(ref).exists()
                else "首次会从网上下载；国内网络请先跑 python -m uediag.fetch_model")
        print(f"[知识库] 加载 {ref}（{hint}）……")
        _st_model = SentenceTransformer(ref)
    vectors = _st_model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
    return [list(map(float, v)) for v in vectors]


def _mock_vector(text: str, dim: int = 256) -> list[float]:
    """确定性的词袋伪向量：同词命中会真的更相似，够单测用（crc32 避免 hash 随机化）。"""
    vec = [0.0] * dim
    for tok in _tokens(text):
        vec[zlib.crc32(tok.encode("utf-8")) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ── Chroma ───────────────────────────────────────────────────
_dim_cache: int | None = None


def embed_dim() -> int:
    """当前编码后端产出的向量维度（真模型 1024 / mock 256）。"""
    global _dim_cache
    if _dim_cache is None:
        _dim_cache = len(encode(["probe"])[0])
    return _dim_cache


def embed_key() -> str:
    return f"{cfg('EMBED_BACKEND')}:{cfg('EMBED_MODEL')}:{embed_dim()}"


def collection(recreate: bool = False):
    import chromadb  # 延迟导入

    client = chromadb.PersistentClient(path=cfg("CHROMA_PATH"))
    if recreate:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "embed_key": embed_key()}
    )


def rebuild(full: bool = False) -> str:
    """知识库 → 向量 → Chroma。幂等：content_hash 没变就跳过编码。返回一行摘要。"""
    cases = load_cases()
    if not cases:
        return f"[知识库] {cfg('KNOWLEDGE_DIR')} 里没有 case（*.md），先写几条再来"

    col = collection()
    key = embed_key()
    note = ""
    if col.count() > 0 and (col.metadata or {}).get("embed_key") != key:
        # 换过编码后端（比如 mock ↔ 真模型）→ 维度不同，整柜重建
        col = collection(recreate=True)
        full = True
        note = "（编码方式变化，已重建集合）"

    existing = col.get(include=["metadatas"])
    old = {i: (m or {}).get("content_hash", "") for i, m in zip(existing["ids"], existing["metadatas"])}

    todo = cases if full else [c for c in cases if old.get(c.id) != c.content_hash]
    if todo:
        col.upsert(
            ids=[c.id for c in todo],
            embeddings=encode([c.embed_text for c in todo]),
            documents=[c.body for c in todo],
            metadatas=[_meta(c) for c in todo],
        )
    orphans = [i for i in old if i not in {c.id for c in cases}]
    if orphans:
        col.delete(ids=orphans)

    return (
        f"[知识库] 入库 {len(todo)}/{len(cases)} 条（跳过 {len(cases) - len(todo)} 条未变）"
        f"，清理孤儿 {len(orphans)} 条，当前共 {col.count()} 条{note}"
    )


def stats() -> str:
    """一致性自查：文件数 vs 文档数。改了 md 忘了重建，这里会不一致。"""
    files = [c.id for c in load_cases()]
    col = collection()
    stored = col.get()["ids"]
    missing = sorted(set(files) - set(stored))
    orphan = sorted(set(stored) - set(files))
    ok = not missing and not orphan
    lines = [f"[知识库] 文件 {len(files)} 条 / 向量库 {len(stored)} 条 —— {'一致' if ok else '不一致！'}"]
    if missing:
        lines.append(f"  未入库: {missing} → 跑 kb rebuild")
    if orphan:
        lines.append(f"  已成孤儿: {orphan} → 跑 kb rebuild --full")
    return "\n".join(lines)


def _meta(c: Case) -> dict[str, Any]:
    """Chroma 的 metadata 只接受标量 → 列表用 | 拼。"""
    return {
        "title": c.title,
        "category": c.category,
        "keywords": "|".join(c.keywords),
        "error_codes": "|".join(c.error_codes),
        "path": c.path,
        "source_url": c.source_url or "",
        "content_hash": c.content_hash,
    }


# ── 检索：BM25 / 向量 / 双轨 ───────────────────────────────────
def search_kb(query: str, top_k: int | None = None) -> list[RetrievedDoc]:
    """对外唯一检索入口。RETRIEVER 决定走哪条路：

    - `hybrid`（默认）：稠密（BGE-M3 + Chroma）+ 稀疏（BM25）→ RRF 融合
    - `vector`：只用稠密轨（查询时仍需编码 query）
    - `bm25`  ：只用关键词轨 —— **不加载模型、不访问向量库**，启动瞬时、可离线
    """
    top_k = top_k or cfg_int("TOP_K")
    mode = cfg("RETRIEVER").strip().lower()

    if mode == "bm25":
        cases = {c.id: c for c in load_cases()}
        if not cases:
            return []
        hits = Bm25(list(cases.values())).search(query, top=top_k)
        return [_doc_from_case(cases[i], s) for i, s in hits]

    col = collection()
    if col.count() == 0:
        return []

    n = max(top_k * 3, 10)
    dense = col.query(query_embeddings=encode([query], kind="query"), n_results=n,
                      include=["documents", "metadatas", "distances"])
    dense_ids = list(dense["ids"][0])

    if mode == "vector":
        fused = [(i, 1.0 - j * 0.01) for j, i in enumerate(dense_ids)]
    else:
        sparse_ids = [i for i, _ in Bm25(load_cases()).search(query, top=n)]
        fused = _rrf([dense_ids, sparse_ids], k=cfg_int("RRF_K"))

    docs_by_id = {
        i: (d, m) for i, d, m in zip(dense["ids"][0], dense["documents"][0], dense["metadatas"][0])
    }
    out: list[RetrievedDoc] = []
    for doc_id, score in fused[:top_k]:
        doc, meta = docs_by_id.get(doc_id, (None, None))
        if doc is None:                        # BM25 命中但稠密轨没召回 → 回库取
            got = col.get(ids=[doc_id], include=["documents", "metadatas"])
            if not got["ids"]:
                continue
            doc, meta = got["documents"][0], got["metadatas"][0]
        meta = meta or {}
        out.append(
            RetrievedDoc(
                doc_id=doc_id,
                title=meta.get("title", doc_id),
                score=float(score),
                body=doc or "",
                path=meta.get("path", ""),
                source_url=meta.get("source_url") or None,
                error_codes=[x for x in (meta.get("error_codes") or "").split("|") if x],
            )
        )
    return out


def _doc_from_case(case: Case, score: float) -> RetrievedDoc:
    return RetrievedDoc(doc_id=case.id, title=case.title, score=float(score), body=case.body,
                        path=case.path, source_url=case.source_url, error_codes=case.error_codes)


def _rrf(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion：只用排名，免调两路分数量纲。"""
    scores: dict[str, float] = {}
    for ids in rank_lists:
        for rank, doc_id in enumerate(ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


# ── 手写 BM25（20 篇文档不需要倒排索引，线性打分即可）──────────
class Bm25:
    K1, B = 1.2, 0.75

    def __init__(self, cases: list[Case]):
        self.docs = {c.id: _tokens(c.bm25_text) for c in cases}
        self.avgdl = sum(len(t) for t in self.docs.values()) / max(len(self.docs), 1)
        self.df = Counter(t for toks in self.docs.values() for t in set(toks))

    def score(self, query: str, doc_id: str) -> float:
        toks = self.docs[doc_id]
        tf_all = Counter(toks)
        dl = len(toks) or 1
        total = 0.0
        for t in _tokens(query):
            tf = tf_all[t]
            if not tf:
                continue
            idf = math.log(1 + (len(self.docs) - self.df[t] + 0.5) / (self.df[t] + 0.5))
            total += idf * tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * dl / self.avgdl))
        return total

    def search(self, query: str, top: int = 10) -> list[tuple[str, float]]:
        scored = [(i, self.score(query, i)) for i in self.docs]
        return sorted((x for x in scored if x[1] > 0), key=lambda kv: -kv[1])[:top]


ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]+")


def _tokens(text: str) -> list[str]:
    """中英符号混排分词：标识符拆开 + 中文 2-gram（不引 jieba）。"""
    text = text.lower()
    out: list[str] = []
    for w in ASCII_WORD.findall(text):
        out.append(w)
        if any(ch in w for ch in ".:_/"):       # UMyTank::OnFire → umytank, onfire
            out.extend(p for p in re.split(r"[.:_/]+", w) if len(p) > 2)
    for seg in CJK.findall(text):
        out.extend(seg[i : i + 2] for i in range(len(seg) - 1))
        if len(seg) == 1:
            out.append(seg)
    return out
