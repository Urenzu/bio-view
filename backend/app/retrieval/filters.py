def build_where(
    sources: list[str] | None = None,
    subjects: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    dois: list[str] | None = None,
) -> dict | None:
    clauses: list[dict] = []
    if sources:
        clauses.append({"source": {"$in": sources}})
    if subjects:
        clauses.append({"subject": {"$in": subjects}})
    if dois:
        clauses.append({"doi": {"$in": dois}})
    if date_from:
        clauses.append({"posted_date": {"$gte": date_from}})
    if date_to:
        clauses.append({"posted_date": {"$lte": date_to}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
