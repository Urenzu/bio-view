from sentence_transformers import SentenceTransformer
from app.embeddings.base import EmbeddingProvider


class HuggingFaceEmbedding:
    def __init__(self, model_id: str, device: str | None = None):
        self.model_id = model_id
        self._model = SentenceTransformer(model_id, device=device)
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = get_dim()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vecs.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


def make_embedding_provider(model_id: str) -> EmbeddingProvider:
    return HuggingFaceEmbedding(model_id)
