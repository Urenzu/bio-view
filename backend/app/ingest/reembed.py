"""Re-embed already-ingested papers into a new Chroma collection.

Iterates Paper rows whose `embedded_in[]` is missing the target model_id,
re-parses the cached JATS XML (no S3, no MECA), chunks, embeds, and upserts
into a new per-model Chroma collection. The original collection stays intact
for live serving while the new one is built.
"""
import argparse
import logging
from pathlib import Path

from app.config import settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.huggingface import make_embedding_provider
from app.ingest import chunker, meca
from app.storage.chroma import get_or_create_collection
from app.storage.ledger import Paper, init_db, session_scope

log = logging.getLogger(__name__)


def _build_metadatas(parsed: meca.ParsedPaper, chunks, source: str) -> tuple[list[str], list[dict]]:
    authors_str = ", ".join(
        f"{a.get('given', '')} {a.get('surname', '')}".strip() for a in parsed.authors
    )[:1000]
    ids = [f"{parsed.doi}::v{parsed.version}::{c.chunk_index}" for c in chunks]
    metadatas = [
        {
            "doi": parsed.doi,
            "version": parsed.version,
            "source": source,
            "subject": parsed.subject or "",
            "title": parsed.title,
            "section": c.section,
            "posted_date": parsed.posted_date or "",
            "authors_str": authors_str,
        }
        for c in chunks
    ]
    return ids, metadatas


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
    log.info("re-embedding %d papers into collection for %s", len(targets), embedding.model_id)

    collection = get_or_create_collection(embedding.model_id)
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
                log.info("no chunks for %s, skipping", doi)
                continue

            texts = [c.text for c in chunks]
            vectors = embedding.embed(texts)
            ids, metadatas = _build_metadatas(parsed, chunks, source)

            try:
                collection.delete(where={"doi": doi})
            except Exception:
                pass
            collection.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas)

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
    p = argparse.ArgumentParser(description="Re-embed cached papers into a new collection")
    p.add_argument(
        "--embedding-model",
        required=True,
        help="HF model id, e.g. NeuML/pubmedbert-base-embeddings",
    )
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    init_db()
    embedding = make_embedding_provider(args.embedding_model)
    reembed(embedding, limit=args.limit)


if __name__ == "__main__":
    main()
