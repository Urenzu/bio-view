from typing import AsyncIterator
from openai import AsyncOpenAI
from app.config import settings

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=_BASE_URL,
        )

    async def generate(self, system: str, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def make_llm_provider(model_id: str) -> OpenRouterProvider:
    return OpenRouterProvider(model_id)
