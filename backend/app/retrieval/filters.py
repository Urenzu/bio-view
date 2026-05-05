from typing import Any


def build_where(
    sources: list[str] | None = None,
    subjects: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    dois: list[str] | None = None,
    authors_contains: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a SQL WHERE fragment + params dict for chunk-table queries."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if sources:
        clauses.append("source = ANY(:sources)")
        params["sources"] = list(sources)
    if subjects:
        clauses.append("subject = ANY(:subjects)")
        params["subjects"] = list(subjects)
    if dois:
        clauses.append("doi = ANY(:dois)")
        params["dois"] = list(dois)
    if date_from:
        clauses.append("posted_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("posted_date <= :date_to")
        params["date_to"] = date_to
    if authors_contains:
        clauses.append("authors_str ILIKE :authors_contains")
        params["authors_contains"] = f"%{authors_contains}%"

    return (" AND ".join(clauses), params)
