import re
import chromadb
from app.config import settings

_client: chromadb.ClientAPI | None = None


def client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _client


def collection_name(embedding_model_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", embedding_model_id)
    return f"papers__{safe}"


def get_or_create_collection(embedding_model_id: str):
    return client().get_or_create_collection(
        name=collection_name(embedding_model_id),
        metadata={"hnsw:space": "cosine", "embedding_model_id": embedding_model_id},
    )
