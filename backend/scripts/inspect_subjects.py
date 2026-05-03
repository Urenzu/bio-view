from sqlalchemy import func
from app.storage.ledger import session_scope, Paper

with session_scope() as s:
    rows = (
        s.query(Paper.source, Paper.subject, func.count(Paper.id))
        .group_by(Paper.source, Paper.subject)
        .order_by(func.count(Paper.id).desc())
        .all()
    )
    print(f"{'count':>5}  {'source':8}  subject")
    print("-" * 50)
    for src, sub, n in rows:
        print(f"{n:>5}  {src:8}  {sub or '-'}")

    print()
    src_totals = (
        s.query(Paper.source, func.count(Paper.id))
        .group_by(Paper.source)
        .all()
    )
    for src, n in src_totals:
        print(f"  {src}: {n}")
