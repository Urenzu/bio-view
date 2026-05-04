from dataclasses import dataclass, asdict

from qdrant_client.models import FieldCondition, Filter, MatchText

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.reranking.base import Reranker
from app.storage.qdrant import client as qdrant_client, get_or_create_collection


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
    where: Filter | None = None,
    top_k: int | None = None,
    authors_contains: str | None = None,
) -> list[Hit]:
    top_k = top_k or settings.retrieval_top_k
    col = get_or_create_collection(embedding.model_id)
    qvec = embedding.embed_query(query)

    qdrant_filter = where
    if authors_contains:
        condition = FieldCondition(key="authors_str", match=MatchText(text=authors_contains))
        if qdrant_filter is None:
            qdrant_filter = Filter(must=[condition])
        else:
            qdrant_filter = Filter(must=list(qdrant_filter.must or []) + [condition])

    results = qdrant_client().query_points(
        collection_name=col,
        query=qvec,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    ).points

    if not results:
        return []

    docs = [r.payload["text"] for r in results]
    metas = [r.payload for r in results]

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
