import logging
from dataclasses import dataclass, asdict
from typing import Any

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.storage import pgvector as pg

log = logging.getLogger(__name__)


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
    rows: list[dict],
    min_k: int,
    max_k: int,
    score_floor: float,
) -> list[dict]:
    """Trim a score-desc-sorted list using top-relative floor + largest-gap.

    1. Cap at max_k.
    2. Drop anything more than `score_floor` below the top score.
    3. Among remaining (beyond min_k), cut at the largest consecutive gap.
    """
    if not rows:
        return []
    rows = rows[:max_k]
    top = rows[0]["score"]

    cap = len(rows)
    for i, r in enumerate(rows):
        if r["score"] < top - score_floor:
            cap = i
            break
    rows = rows[:cap]
    if len(rows) <= min_k:
        return rows

    best_gap = -1.0
    cut = len(rows)
    for i in range(min_k - 1, len(rows) - 1):
        gap = rows[i]["score"] - rows[i + 1]["score"]
        if gap > best_gap:
            best_gap = gap
            cut = i + 1
    return rows[:cut]


def search(
    query: str,
    embedding: EmbeddingProvider,
    where: tuple[str, dict[str, Any]] | None = None,
    top_k: int | None = None,
    authors_contains: str | None = None,
) -> list[Hit]:
    top_k = top_k or settings.retrieval_top_k
    tbl = pg.get_or_create_table(embedding.model_id, dim=embedding.dim)
    qvec = embedding.embed_query(query)

    where_sql, params = where or ("", {})
    if authors_contains:
        extra = "authors_str ILIKE :authors_contains"
        params = {**params, "authors_contains": f"%{authors_contains}%"}
        where_sql = f"({where_sql}) AND {extra}" if where_sql else extra

    rows = pg.search(tbl, qvec, where_sql, params, top_k)
    if not rows:
        return []

    rows = _adaptive_cut(
        rows,
        min_k=settings.result_min_k,
        max_k=settings.result_max_k,
        score_floor=settings.score_floor,
    )

    return [
        Hit(
            doi=str(r.get("doi", "")),
            version=int(r.get("version", 1)),
            section=str(r.get("section", "")),
            title=str(r.get("title", "")),
            source=str(r.get("source", "")),
            subject=str(r.get("subject", "") or ""),
            posted_date=str(r.get("posted_date", "") or ""),
            authors=str(r.get("authors_str", "") or ""),
            text=str(r.get("text", "")),
            score=float(r["score"]),
        )
        for r in rows
    ]
