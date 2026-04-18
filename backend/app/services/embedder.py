import asyncio
import logging
import time
from typing import List

from openai import AsyncOpenAI, RateLimitError

from app.core.config import settings
from app.services.chunker import ChunkData

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model
        self.dimensions = settings.openai_embedding_dimensions
        self.batch_size = settings.embedding_batch_size
        self.rate_limit_rpm = settings.embedding_rate_limit_rpm
        self._window_start = time.time()
        self._requests_in_window = 0

    async def embed_chunks(self, chunks: List[ChunkData]) -> List[List[float]]:
        return await self.embed_texts([chunk.text for chunk in chunks])

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        filtered = [text.strip() for text in texts if text and text.strip()]
        if not filtered:
            return []

        batches = [filtered[i : i + self.batch_size] for i in range(0, len(filtered), self.batch_size)]
        all_embeddings: List[List[float]] = []

        for idx, batch in enumerate(batches, start=1):
            await self._respect_rate_limit()
            logger.info("Embedding batch %s/%s (%s chunks total)", idx, len(batches), len(filtered))
            embeddings = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def _embed_batch_with_retry(self, batch: List[str], max_retries: int = 3) -> List[List[float]]:
        retry = 0
        while True:
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                )
                self._requests_in_window += 1
                return [item.embedding for item in response.data]
            except RateLimitError:
                retry += 1
                if retry > max_retries:
                    raise
                delay = 2**retry
                await asyncio.sleep(delay)

    async def _respect_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._window_start
        if elapsed >= 60:
            self._window_start = now
            self._requests_in_window = 0
            return
        if self._requests_in_window >= self.rate_limit_rpm:
            await asyncio.sleep(60 - elapsed)
            self._window_start = time.time()
            self._requests_in_window = 0
