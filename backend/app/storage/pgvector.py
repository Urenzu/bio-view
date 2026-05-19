"""pgvector-backed chunk store.

One table per embedding model (`chunks__<safe_model_id>`) so different
embedding spaces don't collide and each table can have its own vector column
with the right dimensionality. Mirrors the per-collection pattern previously
used with Qdrant.
"""
import re
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Index,
    MetaData,
    Table,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.storage.ledger import engine


_table_cache: dict[str, Table] = {}


def _safe(model_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", model_id).lower()


def table_name(embedding_model_id: str) -> str:
    return f"chunks__{_safe(embedding_model_id)}"


def _build_table(name: str, dim: int) -> Table:
    md = MetaData()
    return Table(
        name,
        md,
        Column("id", String, primary_key=True),
        Column("doi", String, nullable=False, index=True),
        Column("version", Integer, nullable=False),
        Column("source", String, nullable=False, index=True),
        Column("subject", String, index=True),
        Column("title", Text),
        Column("section", String),
        Column("posted_date", String, index=True),
        Column("authors_str", String),
        Column("text", Text, nullable=False),
        Column("embedding", Vector(dim), nullable=False),
    )


def get_or_create_table(embedding_model_id: str, dim: int | None = None) -> Table:
    name = table_name(embedding_model_id)
    if name in _table_cache:
        return _table_cache[name]

    dim = dim or settings.embedding_dim
    with engine.begin() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    tbl = _build_table(name, dim)
    tbl.create(bind=engine, checkfirst=True)

    # Cosine similarity ANN index. Use IVFFlat which is broadly available and
    # cheap to build; HNSW is also fine if the user has pgvector >= 0.5.
    with engine.begin() as conn:
        conn.execute(
            sql_text(
                f"CREATE INDEX IF NOT EXISTS {name}_embedding_idx "
                f"ON {name} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            )
        )
        conn.execute(
            sql_text(
                f"CREATE INDEX IF NOT EXISTS {name}_authors_trgm "
                f"ON {name} USING gin (authors_str gin_trgm_ops)"
            )
        )
        # Full-text search column for the lexical arm of hybrid retrieval.
        # Generated column auto-maintains itself on insert/update, so the rest
        # of the ingestion path is untouched. Idempotent: ALTER ADD IF NOT EXISTS
        # is supported on Postgres 12+ (Railway pg16 is fine).
        # Bump maintenance_work_mem locally so the one-time backfill across
        # potentially large existing tables doesn't hit the default 64MB cap.
        conn.execute(sql_text("SET LOCAL maintenance_work_mem = '256MB'"))
        conn.execute(
            sql_text(
                f"ALTER TABLE {name} ADD COLUMN IF NOT EXISTS text_tsv tsvector "
                f"GENERATED ALWAYS AS (to_tsvector('english', "
                f"coalesce(title,'') || ' ' || coalesce(text,''))) STORED"
            )
        )
        conn.execute(
            sql_text(
                f"CREATE INDEX IF NOT EXISTS {name}_text_tsv_idx "
                f"ON {name} USING gin (text_tsv)"
            )
        )

    _table_cache[name] = tbl
    return tbl


def ensure_trgm_extension() -> None:
    with engine.begin() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def delete_by_doi(tbl: Table, doi: str) -> None:
    with engine.begin() as conn:
        conn.execute(tbl.delete().where(tbl.c.doi == doi))


def upsert_chunks(tbl: Table, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        stmt = pg_insert(tbl).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c.name: stmt.excluded[c.name] for c in tbl.c if c.name != "id"},
        )
        conn.execute(stmt)


def search(
    tbl: Table,
    qvec: list[float],
    where_sql: str,
    params: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """Cosine-similarity search; returns rows ordered by similarity desc.

    `where_sql` is an additional SQL fragment (without leading WHERE) or "".
    `params` holds named parameters referenced by `where_sql`.
    """
    where_clause = f"WHERE {where_sql}" if where_sql else ""
    sql = sql_text(
        f"""
        SELECT doi, version, source, subject, title, section, posted_date,
               authors_str, text, 1 - (embedding <=> CAST(:qvec AS vector)) AS score
        FROM {tbl.name}
        {where_clause}
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :lim
        """
    )
    params = {**params, "qvec": str(list(qvec)), "lim": limit}
    with engine.connect() as conn:
        result = conn.execute(sql, params)
        return [dict(r._mapping) for r in result]


# RRF constant from the original paper; robust enough it rarely needs tuning.
_RRF_K = 60


def search_hybrid(
    tbl: Table,
    qvec: list[float],
    qtext: str,
    where_sql: str,
    params: dict[str, Any],
    limit: int,
    per_arm: int = 50,
) -> list[dict[str, Any]]:
    """Hybrid vector + lexical search fused with Reciprocal Rank Fusion.

    Runs ANN cosine and Postgres FTS in parallel as CTEs in a single round-trip,
    then fuses by reciprocal-rank. `score` on returned rows is the RRF score,
    not cosine similarity.
    """
    where_clause = f"AND ({where_sql})" if where_sql else ""
    sql = sql_text(
        f"""
        WITH vec AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS vrank
            FROM {tbl.name}
            WHERE TRUE {where_clause}
            ORDER BY embedding <=> CAST(:qvec AS vector)
            LIMIT :per_arm
        ),
        lex AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(text_tsv, plainto_tsquery('english', :qtext)) DESC
                   ) AS lrank
            FROM {tbl.name}
            WHERE text_tsv @@ plainto_tsquery('english', :qtext) {where_clause}
            LIMIT :per_arm
        ),
        fused AS (
            SELECT COALESCE(vec.id, lex.id) AS id,
                   COALESCE(1.0 / ({_RRF_K} + vec.vrank), 0)
                   + COALESCE(1.0 / ({_RRF_K} + lex.lrank), 0) AS score
            FROM vec FULL OUTER JOIN lex USING (id)
        )
        SELECT t.doi, t.version, t.source, t.subject, t.title, t.section,
               t.posted_date, t.authors_str, t.text, fused.score
        FROM fused
        JOIN {tbl.name} t USING (id)
        ORDER BY fused.score DESC
        LIMIT :lim
        """
    )
    params = {
        **params,
        "qvec": str(list(qvec)),
        "qtext": qtext,
        "per_arm": per_arm,
        "lim": limit,
    }
    with engine.connect() as conn:
        result = conn.execute(sql, params)
        return [dict(r._mapping) for r in result]
