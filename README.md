# bio-view

Local-first biomedical preprint search and QA over bioRxiv / medRxiv.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI |
| Database | PostgreSQL (SQLite fallback for local dev) |
| Vector store | Qdrant |
| Ingestion | S3 (Requester Pays) → MECA archive → JATS XML → section-aware chunks |
| Embeddings | `NeuML/pubmedbert-base-embeddings` (local, GPU) |
| Reranker | `ncbi/MedCPT-Cross-Encoder` (local, GPU) |
| Generation | Qwen3-30B-A3B-Instruct via OpenRouter |
| Frontend | Vite + React + TypeScript |

## Quick start (Docker)

```bash
cp .env.example .env
# Fill in AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY, OPENROUTER_API_KEY

docker compose up --build
```

The backend serves the built frontend at `http://localhost:8000`.  
Postgres and Qdrant data are persisted in named Docker volumes.

## Local dev (no Docker)

```bash
# 1. Start Postgres and Qdrant however you like, then set in .env:
#    DATABASE_URL=postgresql://...
#    QDRANT_URL=http://localhost:6333

# 2. Backend (requires uv: https://docs.astral.sh/uv)
cd backend
uv sync
uv pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu121
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (Vite proxies /ask /search /papers /health → :8000)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

SQLite is used automatically if `DATABASE_URL` is not set, writing to `data/bio_view.db`.

## Manual ingest

```bash
cd backend && uv run python -m app.ingest.cli --limit 5
```

Ingest also runs automatically on a monthly cron (`poll_cron`, default 06:00 UTC on the 1st).

## Configuration

All knobs live in `backend/app/config.py` and can be overridden with environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL_ID` | `NeuML/pubmedbert-base-embeddings` | HuggingFace embedding model |
| `RERANKER_MODEL_ID` | `ncbi/MedCPT-Cross-Encoder` | HuggingFace cross-encoder reranker |
| `GEN_MODEL_ID` | `qwen/qwen3-30b-a3b-instruct-2507` | OpenRouter model for generation |
| `RETRIEVAL_TOP_K` | `50` | Vector hits fed to reranker |
| `RERANK_MIN_K` / `RERANK_MAX_K` | `2` / `15` | Adaptive cut bounds |
| `RERANK_SCORE_FLOOR` | `4.0` | Drop hits this many MedCPT logits below top score |
| `MAX_DAILY_GB` | `50.0` | Requester-Pays byte-cap guardrail |
| `EARLIEST_YEAR` | `2026` | Only ingest papers from this year onward |
| `POLL_CRON` | `0 6 1 * *` | Ingest schedule (cron syntax) |

## Design notes

- **Ledger-driven idempotency.** The `papers` table tracks `(doi, version, embedded_in[])`; re-running ingest skips already-embedded rows.
- **Per-model Qdrant collections.** Each embedding model writes to `papers__<safe_model_id>`; swap models without losing the old index.
- **Adaptive source count.** The sources panel shows a query-dependent number of hits (top-relative floor + largest-gap cutoff over MedCPT scores), not a fixed top-N.
- **Model provenance.** `(gen_model_id, embedding_model_id, reranker_model_id)` are stored on every saved message.
- **Conversation persistence.** All Q&A turns are stored in Postgres, keyed by `conversation_id`.
