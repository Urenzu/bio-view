import logging
import random
import shutil
import signal
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterator

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.ingest import chunker, meca, s3
from app.storage import pgvector as pg
from app.storage.ledger import IngestRun, MecaState, Paper, session_scope

log = logging.getLogger(__name__)

SOURCES = [
    ("biorxiv", settings.biorxiv_bucket, settings.biorxiv_prefix),
    ("medrxiv", settings.medrxiv_bucket, settings.medrxiv_prefix),
]


class _Skip(Exception):
    def __init__(self, reason: str, bytes_dl: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.bytes_dl = bytes_dl


_stop_requested = False


def _install_signal_handlers() -> None:
    def _handler(signum, _frame):
        global _stop_requested
        if _stop_requested:
            log.warning("second signal received, exiting hard")
            raise SystemExit(130)
        _stop_requested = True
        log.warning("stop requested (signal %d) — finishing current MECA then exiting", signum)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _should_skip_state(state: MecaState | None, embedding_model_id: str) -> bool:
    """Decide whether to skip processing this MECA based on prior attempts."""
    if state is None:
        return False
    if state.status == "done":
        return True
    if state.status == "skipped":
        return True
    if state.status == "failed" and state.attempt_count >= settings.max_retry_attempts:
        return True
    # "ingesting" means a prior run crashed mid-flight — retry it
    return False


def _record_done(session, key: str, source: str, paper_id: int | None) -> None:
    state = session.query(MecaState).filter_by(meca_key=key).first()
    if state is None:
        state = MecaState(meca_key=key, source=source, status="done", attempt_count=1, paper_id=paper_id)
        session.add(state)
    else:
        state.status = "done"
        state.attempt_count = (state.attempt_count or 0) + 1
        state.last_attempt_at = datetime.utcnow()
        state.paper_id = paper_id
        state.last_error = None


def _record_skip(session, key: str, source: str, reason: str) -> None:
    state = session.query(MecaState).filter_by(meca_key=key).first()
    if state is None:
        state = MecaState(meca_key=key, source=source, status="skipped", skip_reason=reason, attempt_count=1)
        session.add(state)
    else:
        state.status = "skipped"
        state.skip_reason = reason
        state.attempt_count = (state.attempt_count or 0) + 1
        state.last_attempt_at = datetime.utcnow()


def _record_failure(session, key: str, source: str, err: str) -> None:
    state = session.query(MecaState).filter_by(meca_key=key).first()
    if state is None:
        state = MecaState(
            meca_key=key, source=source, status="failed",
            attempt_count=1, last_attempt_at=datetime.utcnow(), last_error=err,
        )
        session.add(state)
    else:
        state.status = "failed"
        state.attempt_count = (state.attempt_count or 0) + 1
        state.last_attempt_at = datetime.utcnow()
        state.last_error = err


def _ingest_one(source: str, bucket: str, key: str, embedding: EmbeddingProvider) -> tuple[int, int | None]:
    """Returns (bytes_downloaded, paper_id). Raises _Skip(reason) for non-fatal skips."""
    meca_path = settings.meca_temp_path / Path(key).name
    extract_dir = settings.meca_temp_path / (Path(key).stem + "_x")

    bytes_dl = s3.download_meca(bucket, key, meca_path)
    try:
        jats_path, _manifest = meca.extract_meca(meca_path, extract_dir)
        if jats_path is None:
            raise _Skip("no_jats", bytes_dl)

        parsed = meca.parse_jats(jats_path)
        if not parsed.doi or not parsed.title:
            raise _Skip("incomplete_jats", bytes_dl)
        if parsed.posted_date and int(parsed.posted_date[:4]) < settings.earliest_year:
            raise _Skip("before_earliest_year", bytes_dl)

        cached_jats = (
            settings.jats_cache_path
            / source
            / f"{parsed.doi.replace('/', '_')}_v{parsed.version}.xml"
        )
        cached_jats.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jats_path, cached_jats)

        chunks = chunker.chunk_paper(parsed)
        if not chunks:
            raise _Skip("no_chunks", bytes_dl)

        texts = [c.text for c in chunks]
        vectors = embedding.embed(texts)

        tbl = pg.get_or_create_table(embedding.model_id, dim=embedding.dim)
        pg.delete_by_doi(tbl, parsed.doi)

        authors_str = ", ".join(
            f"{a.get('given', '')} {a.get('surname', '')}".strip() for a in parsed.authors
        )[:1000]

        rows = [
            {
                "id": f"{parsed.doi}::v{parsed.version}::{chunk.chunk_index}",
                "doi": parsed.doi,
                "version": parsed.version,
                "source": source,
                "subject": parsed.subject or "",
                "title": parsed.title,
                "section": chunk.section,
                "posted_date": parsed.posted_date or "",
                "authors_str": authors_str,
                "text": text,
                "embedding": vec,
            }
            for vec, text, chunk in zip(vectors, texts, chunks)
        ]
        pg.upsert_chunks(tbl, rows)

        with session_scope() as session:
            existing = (
                session.query(Paper)
                .filter_by(doi=parsed.doi, version=parsed.version)
                .first()
            )
            if existing:
                existing.embedded_in = list(
                    set((existing.embedded_in or []) + [embedding.model_id])
                )
                existing.status = "embedded"
                existing.bytes_downloaded = (existing.bytes_downloaded or 0) + bytes_dl
                paper_id = existing.id
            else:
                p = Paper(
                    doi=parsed.doi,
                    version=parsed.version,
                    source=source,
                    meca_key=key,
                    title=parsed.title,
                    subject=parsed.subject,
                    authors=parsed.authors,
                    posted_date=parsed.posted_date,
                    jats_path=str(cached_jats),
                    embedded_in=[embedding.model_id],
                    status="embedded",
                    bytes_downloaded=bytes_dl,
                )
                session.add(p)
                session.flush()
                paper_id = p.id
        return bytes_dl, paper_id
    finally:
        meca_path.unlink(missing_ok=True)
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)


def _sequential_keys() -> Iterator[tuple[str, str, str]]:
    for source, bucket, prefix in SOURCES:
        for key, _size in s3.list_meca_keys(
            bucket, prefix, min_year=settings.earliest_year
        ):
            yield (source, bucket, key)


def _stratified_sample(target: int, seed: int | None) -> list[tuple[str, str, str]]:
    """Pick `target` MECA keys spread evenly across (source, month) strata.
    Returns a shuffled list of (source, bucket, key)."""
    rng = random.Random(seed)
    strata: list[tuple[str, str, list[str]]] = []
    for source, bucket, prefix in SOURCES:
        try:
            by_month = s3.list_meca_keys_by_month(bucket, prefix, settings.earliest_year)
        except Exception:
            log.exception("failed to list %s", bucket)
            continue
        for month_prefix, keys in by_month.items():
            if keys:
                strata.append((source, bucket, keys))
                log.info("stratum %s/%s: %d keys", source, month_prefix, len(keys))

    if not strata:
        return []

    per_stratum = max(1, target // len(strata))
    sampled: list[tuple[str, str, str]] = []
    used: set[tuple[str, str, str]] = set()
    for source, bucket, keys in strata:
        n = min(per_stratum, len(keys))
        for k in rng.sample(keys, n):
            entry = (source, bucket, k)
            sampled.append(entry)
            used.add(entry)

    leftover = target - len(sampled)
    if leftover > 0:
        pool = [
            (s, b, k)
            for s, b, ks in strata
            for k in ks
            if (s, b, k) not in used
        ]
        for entry in rng.sample(pool, min(leftover, len(pool))):
            sampled.append(entry)

    rng.shuffle(sampled)
    log.info("stratified sample: %d keys across %d strata", len(sampled), len(strata))
    return sampled


def run_ingest(
    embedding: EmbeddingProvider,
    limit: int | None = None,
    sample: int | None = None,
    seed: int | None = None,
) -> int:
    _install_signal_handlers()

    with session_scope() as session:
        run = IngestRun()
        session.add(run)
        session.flush()
        run_id = run.id

    total_bytes = 0
    added = 0
    failed = 0
    processed = 0
    max_bytes = int(settings.max_daily_gb * 1024**3)

    if sample is not None:
        keys: Iterator[tuple[str, str, str]] = iter(_stratified_sample(sample, seed))
    else:
        keys = _sequential_keys()

    for source, bucket, key in keys:
        if _stop_requested:
            log.info("stop requested, exiting cleanly")
            break
        if limit is not None and processed >= limit:
            break
        if total_bytes >= max_bytes:
            log.warning("daily byte cap reached: %d bytes", total_bytes)
            break

        with session_scope() as session:
            state = session.query(MecaState).filter_by(meca_key=key).first()
            paper = session.query(Paper).filter_by(meca_key=key).first()
            already_embedded = paper is not None and embedding.model_id in (paper.embedded_in or [])
        if already_embedded:
            continue
        if _should_skip_state(state, embedding.model_id):
            continue

        with session_scope() as session:
            state = session.query(MecaState).filter_by(meca_key=key).first()
            if state is None:
                session.add(MecaState(
                    meca_key=key, source=source, status="ingesting",
                    attempt_count=1, last_attempt_at=datetime.utcnow(),
                ))
            else:
                state.status = "ingesting"
                state.last_attempt_at = datetime.utcnow()

        try:
            bytes_dl, paper_id = _ingest_one(source, bucket, key, embedding)
            total_bytes += bytes_dl
            added += 1
            processed += 1
            with session_scope() as session:
                _record_done(session, key, source, paper_id)
            log.info("ingested %s/%s (+%d bytes)", source, key, bytes_dl)
        except _Skip as e:
            total_bytes += e.bytes_dl
            with session_scope() as session:
                _record_skip(session, key, source, e.reason)
            log.info("skipped %s/%s: %s", source, key, e.reason)
        except Exception:
            err = traceback.format_exc(limit=3)
            log.exception("failed %s/%s", source, key)
            failed += 1
            processed += 1
            with session_scope() as session:
                _record_failure(session, key, source, err)

    with session_scope() as session:
        r = session.get(IngestRun, run_id)
        r.finished_at = datetime.utcnow()
        r.bytes_downloaded = total_bytes
        r.papers_added = added
        r.papers_failed = failed
        if _stop_requested:
            r.notes = "stopped via signal"
    log.info(
        "ingest run %d done: added=%d failed=%d bytes=%d stopped=%s",
        run_id, added, failed, total_bytes, _stop_requested,
    )
    return run_id
