from typing import Protocol, runtime_checkable


@runtime_checkable
class Reranker(Protocol):
    model_id: str

    def rerank(self, query: str, docs: list[str]) -> list[float]: ...
