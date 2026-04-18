from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

import redis.asyncio as redis

from app.core.config import settings
from app.services.pipeline.base import PipelineResult, pipeline_result_from_serializable, pipeline_result_to_serializable

logger = logging.getLogger(__name__)


class ContextCache:
    def __init__(self) -> None:
        self._redis: Optional[redis.Redis] = None
        self.ttl = settings.context_cache_ttl_seconds
        self.max_keys = settings.context_cache_max_keys
        self.prefix = "noesis:ctx:"
        self.index_key = "noesis:ctx:index"

    def _client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def _key(self, url: str, title: str) -> str:
        raw = f"{url}::{title}"
        return f"{self.prefix}{hashlib.sha256(raw.encode()).hexdigest()}"

    async def _evict_excess(self, r: redis.Redis) -> None:
        try:
            while await r.zcard(self.index_key) > self.max_keys:
                popped = await r.zpopmin(self.index_key, 1)
                if not popped:
                    break
                key, _score = popped[0]
                await r.delete(key)
        except Exception as e:
            logger.warning("Cache eviction failed: %s", e)

    async def get(self, url: str, title: str) -> Optional[PipelineResult]:
        try:
            r = self._client()
            raw = await r.get(self._key(url, title))
            if not raw:
                return None
            data = json.loads(raw)
            return pipeline_result_from_serializable(data)
        except Exception as e:
            logger.warning("Cache get failed: %s", e)
            return None

    async def set(self, url: str, title: str, result: PipelineResult) -> None:
        try:
            r = self._client()
            key = self._key(url, title)
            payload = json.dumps(pipeline_result_to_serializable(result))
            await r.setex(key, self.ttl, payload)
            await r.zadd(self.index_key, {key: time.time()})
            await self._evict_excess(r)
        except Exception as e:
            logger.warning("Cache set failed: %s", e)

    async def invalidate(self, url: str, title: str) -> None:
        try:
            r = self._client()
            key = self._key(url, title)
            await r.delete(key)
            await r.zrem(self.index_key, key)
        except Exception as e:
            logger.warning("Cache invalidate failed: %s", e)
