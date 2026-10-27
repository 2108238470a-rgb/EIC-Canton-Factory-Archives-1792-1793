"""OpenAI-compatible embedding client."""

from typing import List, Optional

from httpx import Timeout
from openai import APIError, AsyncOpenAI

from app.config import settings
from app.core import GPTServiceError

MAX_INPUT_CHARS = 4000


class EmbeddingService:
    """Embed texts with the configured provider (bge-m3 by default)."""

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or settings.embedding_model

    def _client(self) -> AsyncOpenAI:
        api_key = settings.gpt_api_key.strip()
        if not api_key:
            raise GPTServiceError(
                "GPT_API_KEY is not configured; embeddings are unavailable."
            )
        return AsyncOpenAI(
            api_key=api_key,
            base_url=settings.gpt_base_url,
            timeout=Timeout(60.0, connect=15.0),
            max_retries=settings.gpt_max_retries,
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts in provider-sized batches, preserving input order.

        Args:
            texts: Non-empty strings to embed.

        Returns:
            One vector per input text.

        Raises:
            GPTServiceError: If the provider rejects or fails the request.
        """
        if not texts:
            return []
        batch_size = max(1, settings.embedding_batch_size)
        vectors: List[List[float]] = []
        try:
            async with self._client() as client:
                for start in range(0, len(texts), batch_size):
                    batch = [
                        text[:MAX_INPUT_CHARS]
                        for text in texts[start : start + batch_size]
                    ]
                    response = await client.embeddings.create(
                        model=self.model, input=batch
                    )
                    ordered = sorted(response.data, key=lambda item: item.index)
                    vectors.extend(item.embedding for item in ordered)
        except APIError as exc:
            raise GPTServiceError("Embedding request failed", str(exc)[:200]) from exc
        return vectors
