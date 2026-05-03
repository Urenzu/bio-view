from sentence_transformers import CrossEncoder


class BGEReranker:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self._model = CrossEncoder(model_id)

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        pairs = [[query, d] for d in docs]
        scores = self._model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]


def make_reranker(model_id: str) -> BGEReranker:
    return BGEReranker(model_id)
