import re
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)

from app.config import settings

_client: QdrantClient | None = None

# Deterministic UUID namespace for chunk IDs
_CHUNK_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _client


def collection_name(embedding_model_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", embedding_model_id)
    return f"papers__{safe}"


def chunk_uuid(chunk_id: str) -> str:
    """Deterministic UUID5 from a string chunk ID, safe for Qdrant point IDs."""
    return str(uuid.uuid5(_CHUNK_NS, chunk_id))


def get_or_create_collection(embedding_model_id: str) -> str:
    """Return collection name, creating it with indexes if it doesn't exist."""
    name = collection_name(embedding_model_id)
    existing = {c.name for c in client().get_collections().collections}
    if name not in existing:
        client().create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        _create_payload_indexes(name)
    return name


def _create_payload_indexes(name: str) -> None:
    text_index = TextIndexParams(
        type="text",
        tokenizer=TokenizerType.WORD,
        lowercase=True,
    )
    client().create_payload_index(name, "authors_str", text_index)
    client().create_payload_index(name, "text", text_index)
