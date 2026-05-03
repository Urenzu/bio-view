import argparse
import logging

from app.config import settings
from app.embeddings.huggingface import make_embedding_provider
from app.ingest.pipeline import run_ingest
from app.storage.ledger import init_db


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    p = argparse.ArgumentParser(description="bio-view ingest CLI")
    p.add_argument("--limit", type=int, default=None, help="max papers to process this run")
    p.add_argument(
        "--sample",
        type=int,
        default=None,
        help="stratified random sample across (source x month) strata; pass target N",
    )
    p.add_argument("--seed", type=int, default=None, help="RNG seed for --sample (reproducible)")
    p.add_argument("--embedding-model", default=settings.embedding_model_id)
    args = p.parse_args()

    init_db()
    embedding = make_embedding_provider(args.embedding_model)
    run_id = run_ingest(embedding, limit=args.limit, sample=args.sample, seed=args.seed)
    print(f"ingest run complete: id={run_id}")


if __name__ == "__main__":
    main()
