from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import get_embedding, get_reranker
from app.retrieval.filters import build_where
from app.retrieval.search import Hit, search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    sources: list[str] | None = None
    subjects: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    dois: list[str] | None = None
    authors_contains: str | None = None
    top_k: int | None = None


@router.post("/search")
def post_search(req: SearchRequest) -> list[dict]:
    where = build_where(
        sources=req.sources,
        subjects=req.subjects,
        date_from=req.date_from,
        date_to=req.date_to,
        dois=req.dois,
    )
    hits: list[Hit] = search(
        req.query,
        get_embedding(),
        get_reranker(),
        where=where,
        top_k=req.top_k,
        authors_contains=req.authors_contains,
    )
    return [h.to_dict() for h in hits]
