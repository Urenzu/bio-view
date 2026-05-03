from dataclasses import dataclass, asdict
from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.reranking.base import Reranker
from app.storage.chroma import get_or_create_collection


@dataclass
class Hit:
    doi: str
    version: int
    section: str
    title: str
    source: str
    subject: str
    posted_date: str
    authors: str
    text: str
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def _adaptive_cut(
    ranked: list[tuple],
    min_k: int,
    max_k: int,
    score_floor: float,
) -> list[tuple]:
    """Trim a score-desc-sorted list using top-relative floor + largest-gap.

    1. Cap at max_k.
    2. Drop anything more than `score_floor` below the top score.
    3. Among remaining (beyond min_k), cut at the largest consecutive gap.
    """
    if not ranked:
        return []
    ranked = ranked[:max_k]
    top = ranked[0][-1]

    cap = len(ranked)
    for i, item in enumerate(ranked):
        if item[-1] < top - score_floor:
            cap = i
            break
    ranked = ranked[:cap]
    if len(ranked) <= min_k:
        return ranked

    best_gap = -1.0
    cut = len(ranked)
    for i in range(min_k - 1, len(ranked) - 1):
        gap = ranked[i][-1] - ranked[i + 1][-1]
        if gap > best_gap:
            best_gap = gap
            cut = i + 1
    return ranked[:cut]


def search(
    query: str,
    embedding: EmbeddingProvider,
    reranker: Reranker,
    where: dict | None = None,
    top_k: int | None = None,
    authors_contains: str | None = None,
) -> list[Hit]:
    top_k = top_k or settings.retrieval_top_k

    collection = get_or_create_collection(embedding.model_id)
    qvec = embedding.embed_query(query)

    args: dict = {
        "query_embeddings": [qvec],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        args["where"] = where
    if authors_contains:
        args["where_document"] = {"$contains": authors_contains}

    res = collection.query(**args)
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    if not docs:
        return []

    scores = reranker.rerank(query, docs)
    ranked = sorted(zip(docs, metas, scores), key=lambda x: x[2], reverse=True)
    ranked = _adaptive_cut(
        ranked,
        min_k=settings.rerank_min_k,
        max_k=settings.rerank_max_k,
        score_floor=settings.rerank_score_floor,
    )

    return [
        Hit(
            doi=str(m.get("doi", "")),
            version=int(m.get("version", 1)),
            section=str(m.get("section", "")),
            title=str(m.get("title", "")),
            source=str(m.get("source", "")),
            subject=str(m.get("subject", "")),
            posted_date=str(m.get("posted_date", "")),
            authors=str(m.get("authors_str", "")),
            text=d,
            score=float(s),
        )
        for d, m, s in ranked
    ]
