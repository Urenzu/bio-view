"""Re-embed already-ingested papers into a new pgvector table.

Iterates Paper rows whose `embedded_in[]` is missing the target model_id,
re-parses the cached JATS XML (no S3, no MECA), chunks, embeds, and upserts
into a new per-model pgvector table. The original table stays intact for
live serving while the new one is built.
"""
import argparse
import logging
from pathlib import Path

from app.embeddings.base import EmbeddingProvider
from app.embeddings.openai import make_embedding_provider
from app.ingest import chunker, meca
from app.storage import pgvector as pg
from app.storage.ledger import Paper, init_db, session_scope

log = logging.getLogger(__name__)


def reembed(embedding: EmbeddingProvider, limit: int | None = None) -> None:
    with session_scope() as session:
        rows = (
            session.query(Paper)
            .filter(Paper.status == "embedded")
            .filter(Paper.jats_path.isnot(None))
            .all()
        )
        targets = [
            (p.id, p.doi, p.source, p.jats_path)
            for p in rows
            if embedding.model_id not in (p.embedded_in or [])
        ]

    if limit is not None:
        targets = targets[:limit]
    log.info("re-embedding %d papers into table for %s", len(targets), embedding.model_id)

    tbl = pg.get_or_create_table(embedding.model_id, dim=embedding.dim)
    done = 0
    failed = 0

    for paper_id, doi, source, jats_path in targets:
        try:
            path = Path(jats_path)
            if not path.exists():
                log.warning("missing JATS for %s at %s, skipping", doi, jats_path)
                failed += 1
                continue

            parsed = meca.parse_jats(path)
            chunks = chunker.chunk_paper(parsed)
            if not chunks:
                continue

            texts = [c.text for c in chunks]
            vectors = embedding.embed(texts)

            authors_str = ", ".join(
                f"{a.get('given', '')} {a.get('surname', '')}".strip()
                for a in parsed.authors
            )[:1000]

            pg.delete_by_doi(tbl, doi)
            pg.upsert_chunks(tbl, [
                {
                    "id": f"{doi}::v{parsed.version}::{c.chunk_index}",
                    "doi": doi,
                    "version": parsed.version,
                    "source": source,
                    "subject": parsed.subject or "",
                    "title": parsed.title,
                    "section": c.section,
                    "posted_date": parsed.posted_date or "",
                    "authors_str": authors_str,
                    "text": t,
                    "embedding": v,
                }
                for c, t, v in zip(chunks, texts, vectors)
            ])

            with session_scope() as session:
                fresh = session.get(Paper, paper_id)
                if fresh is not None:
                    fresh.embedded_in = list(set((fresh.embedded_in or []) + [embedding.model_id]))

            done += 1
            log.info("re-embedded %s (%d chunks)", doi, len(chunks))
        except Exception:
            failed += 1
            log.exception("re-embed failed for %s", doi)

    log.info("reembed done: %d ok / %d failed / target=%s", done, failed, embedding.model_id)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    p = argparse.ArgumentParser(description="Re-embed cached papers into a new table")
    p.add_argument("--embedding-model", required=True)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    init_db()
    embedding = make_embedding_provider(args.embedding_model)
    reembed(embedding, limit=args.limit)


if __name__ == "__main__":
    main()
