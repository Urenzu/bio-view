# bio-view

Local-first biomedical preprint search and QA over bioRxiv / medRxiv.

## Stack

- **Backend:** Python 3.11, FastAPI, SQLite (via SQLAlchemy), Chroma vector DB
- **Ingestion:** S3 (Requester Pays) → MECA archive → JATS XML → section-aware chunks
- **Embeddings:** `NeuML/pubmedbert-base-embeddings` (local, GPU)
- **Reranker:** `ncbi/MedCPT-Cross-Encoder` (local, GPU)
- **Generation:** Qwen3-30B-A3B-Instruct via OpenRouter
- **Frontend:** Vite + React + TypeScript

## Setup

```bash
# Backend (uses uv: https://docs.astral.sh/uv)
cd backend
uv sync
uv pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu121

# Frontend
cd ../frontend
npm install

# Secrets — copy and fill in your keys
cp .env.example .env
```

`.env` keys: `AWS_ACCESS_KEY`, `AWS_SECRET_ACCESS_KEY` (S3 Requester Pays for biorxiv/medrxiv buckets), `OPENROUTER_API_KEY`.

## Run

```bash
# Backend (FastAPI on :8000, monthly ingest poller starts automatically)
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend (Vite on :5173, proxies /ask /search /papers /health → :8000)
cd frontend && npm run dev

# Manual ingest
cd backend && uv run python -m app.ingest.cli --limit 5
```

## Configuration

See `backend/app/config.py`. Notable knobs:

- `retrieval_top_k` — vector hits fed to reranker (default 50)
- `rerank_min_k` / `rerank_max_k` — bounds on adaptive cut (default 2 / 15)
- `rerank_score_floor` — drop hits more than this many MedCPT logits below the top score (default 4.0)
- `max_daily_gb` — Requester-Pays byte-cap guardrail

## Design notes

- **Per-model Chroma collections.** Each embedding model writes to `papers__<safe_model_id>`; swap models without losing the old index.
- **Ledger-driven idempotency.** SQLite `papers` table tracks `(doi, version, embedded_in[])`; re-running ingest skips already-embedded rows.
- **Adaptive source count.** The Sources panel shows a query-dependent number of hits (top-relative floor + largest-gap cutoff over MedCPT scores), not a fixed top-10.
- **Model provenance on every message.** `(gen_model_id, embedding_model_id, reranker_model_id)` are stored per saved message.
