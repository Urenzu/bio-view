from qdrant_client.models import FieldCondition, Filter, MatchAny, Range


def build_where(
    sources: list[str] | None = None,
    subjects: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    dois: list[str] | None = None,
) -> Filter | None:
    conditions: list[FieldCondition] = []
    if sources:
        conditions.append(FieldCondition(key="source", match=MatchAny(any=sources)))
    if subjects:
        conditions.append(FieldCondition(key="subject", match=MatchAny(any=subjects)))
    if dois:
        conditions.append(FieldCondition(key="doi", match=MatchAny(any=dois)))
    if date_from:
        conditions.append(FieldCondition(key="posted_date", range=Range(gte=date_from)))
    if date_to:
        conditions.append(FieldCondition(key="posted_date", range=Range(lte=date_to)))
    if not conditions:
        return None
    return Filter(must=conditions)
