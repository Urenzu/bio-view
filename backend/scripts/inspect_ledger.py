from sqlalchemy import func
from app.storage.ledger import session_scope, Paper, MecaState, IngestRun

with session_scope() as s:
    papers = s.query(Paper).all()
    print(f"=== {len(papers)} papers ===\n")
    for p in papers[:20]:
        title = (p.title or "")[:65]
        subj = p.subject or "-"
        print(f"  {p.doi} v{p.version} [{subj}] {title}")
    if len(papers) > 20:
        print(f"  ... and {len(papers) - 20} more")

    print("\n=== MECA states ===")
    counts = (
        s.query(MecaState.status, func.count(MecaState.id))
        .group_by(MecaState.status)
        .all()
    )
    for status, n in counts:
        print(f"  {status}: {n}")

    failed = s.query(MecaState).filter_by(status="failed").limit(5).all()
    if failed:
        print("\n  recent failures:")
        for f in failed:
            err_line = (f.last_error or "").splitlines()[-1] if f.last_error else ""
            print(f"    {f.meca_key} attempts={f.attempt_count} err={err_line[:80]}")

    print("\n=== Ingest runs ===")
    runs = s.query(IngestRun).order_by(IngestRun.id.desc()).limit(5).all()
    for r in runs:
        gb = (r.bytes_downloaded or 0) / 1024**3
        print(
            f"  run {r.id}: added={r.papers_added} failed={r.papers_failed} "
            f"{gb:.2f} GB started={r.started_at} finished={r.finished_at} "
            f"notes={r.notes or ''}"
        )
