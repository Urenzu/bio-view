from fastapi import APIRouter, HTTPException
from app.storage.ledger import Paper, session_scope

router = APIRouter()


def _serialize(p: Paper) -> dict:
    return {
        "doi": p.doi,
        "version": p.version,
        "source": p.source,
        "title": p.title,
        "subject": p.subject,
        "authors": p.authors,
        "posted_date": p.posted_date,
        "status": p.status,
        "embedded_in": p.embedded_in,
    }


@router.get("/papers")
def list_papers(
    source: str | None = None,
    subject: str | None = None,
    limit: int = 50,
) -> list[dict]:
    with session_scope() as s:
        q = s.query(Paper)
        if source:
            q = q.filter_by(source=source)
        if subject:
            q = q.filter_by(subject=subject)
        rows = q.order_by(Paper.posted_date.desc()).limit(limit).all()
        return [_serialize(p) for p in rows]


@router.get("/papers/{doi:path}")
def get_paper(doi: str) -> list[dict]:
    with session_scope() as s:
        rows = (
            s.query(Paper)
            .filter_by(doi=doi)
            .order_by(Paper.version.desc())
            .all()
        )
        if not rows:
            raise HTTPException(status_code=404, detail="paper not found")
        return [_serialize(p) for p in rows]
