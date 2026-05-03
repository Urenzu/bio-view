from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    model_id: str

    async def generate(self, system: str, prompt: str) -> str: ...

    def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...
