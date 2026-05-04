"""Lazily-instantiated singletons for the API surface.

Models are heavy to load (the reranker pulls ~300MB into VRAM/RAM); we want
this to happen once per process, on first use, not on import.
"""
import logging

from app.config import settings
from app.embeddings.huggingface import make_embedding_provider
from app.embeddings.base import EmbeddingProvider
from app.llm.openrouter import make_llm_provider
from app.llm.base import LLMProvider
from app.reranking.bge import make_reranker
from app.reranking.base import Reranker

log = logging.getLogger(__name__)

_embedding: EmbeddingProvider | None = None
_reranker: Reranker | None = None
_llm: LLMProvider | None = None


def get_embedding() -> EmbeddingProvider:
    global _embedding
    if _embedding is None:
        emb = make_embedding_provider(settings.embedding_model_id)
        if emb.dim != settings.embedding_dim:
            raise RuntimeError(
                f"Embedding model '{settings.embedding_model_id}' reports dim={emb.dim} "
                f"but config.embedding_dim={settings.embedding_dim}. "
                f"Set EMBEDDING_DIM={emb.dim} in your environment or update config.py."
            )
        log.info("embedding model loaded: %s dim=%d", settings.embedding_model_id, emb.dim)
        _embedding = emb
    return _embedding


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = make_reranker(settings.reranker_model_id)
    return _reranker


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = make_llm_provider(settings.gen_model_id)
    return _llm
