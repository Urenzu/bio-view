"""Lazily-instantiated singletons for the API surface.

Models are heavy to load (the reranker pulls ~300MB into VRAM/RAM); we want
this to happen once per process, on first use, not on import.
"""
from app.config import settings
from app.embeddings.huggingface import make_embedding_provider
from app.embeddings.base import EmbeddingProvider
from app.llm.openrouter import make_llm_provider
from app.llm.base import LLMProvider
from app.reranking.bge import make_reranker
from app.reranking.base import Reranker

_embedding: EmbeddingProvider | None = None
_reranker: Reranker | None = None
_llm: LLMProvider | None = None


def get_embedding() -> EmbeddingProvider:
    global _embedding
    if _embedding is None:
        _embedding = make_embedding_provider(settings.embedding_model_id)
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
