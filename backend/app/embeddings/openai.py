from openai import OpenAI

from app.config import settings
from app.embeddings.base import EmbeddingProvider


_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedding:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.dim = _MODEL_DIMS.get(model_id, settings.embedding_dim)
        self._client = OpenAI(api_key=settings.openai_api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # OpenAI embeddings endpoint accepts batches; cap at 2048 inputs per call.
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            batch = texts[i : i + 256]
            resp = self._client.embeddings.create(model=self.model_id, input=batch)
            out.extend(d.embedding for d in resp.data)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


def make_embedding_provider(model_id: str) -> EmbeddingProvider:
    return OpenAIEmbedding(model_id)
