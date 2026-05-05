# syntax=docker/dockerfile:1.6

# ── Stage 1: build the React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /frontend

# Cache npm install across rebuilds when package*.json hasn't changed
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

COPY frontend ./
RUN npm run build


# ── Stage 2: build Python deps with uv ────────────────────────────────────────
FROM python:3.11-slim AS backend-build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1

# Build deps for lxml / psycopg2-binary wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps first (cached layer), then project code.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ── Stage 3: minimal runtime image ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    JATS_CACHE_PATH=/tmp/bio-view/jats \
    MECA_TEMP_PATH=/tmp/bio-view/meca_tmp

# Runtime-only shared libs for lxml. No build toolchain in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

WORKDIR /app

COPY --from=backend-build /app/.venv /app/.venv
COPY --from=backend-build /app/app /app/app
COPY --from=frontend-build /frontend/dist /app/static

RUN mkdir -p /tmp/bio-view/jats /tmp/bio-view/meca_tmp \
    && chown -R app:app /app /tmp/bio-view

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

# Shell form so ${PORT} is expanded by Railway / other PaaS at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
