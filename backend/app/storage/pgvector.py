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
