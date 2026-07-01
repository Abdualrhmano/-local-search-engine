# app/storage.py
"""
Visited URL storage abstraction.

Primary: Redis + RedisBloom (using redis.asyncio client).
Fallback: local disk-backed Bloom filter (pybloom_live) if Redis not configured.

This module exposes an async interface:
- async def add(url) -> bool  (True if newly added)
- async def exists(url) -> bool
"""

import asyncio
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger("local_search.storage")

# Try to import redis.asyncio and redisbloom commands
try:
    import redis.asyncio as redis_async
    from redis.commands.bf import BF  # redis-py redisbloom support
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

# Fallback: pybloom_live (synchronous). We'll run it in a threadpool to avoid blocking.
try:
    from pybloom_live import ScalableBloomFilter
    PYBLOOM_AVAILABLE = True
except Exception:
    PYBLOOM_AVAILABLE = False

import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=2)


class RedisBloomVisited:
    def __init__(self, url: str, key: str, capacity: int, error_rate: float):
        self.url = url
        self.key = key
        self.capacity = capacity
        self.error_rate = error_rate
        self._client: Optional["redis_async.Redis"] = None

    async def connect(self):
        if not REDIS_AVAILABLE:
            raise RuntimeError("redis.asyncio not available")
        if self._client is None:
            self._client = redis_async.from_url(self.url, decode_responses=True)
            # Ensure BF.RESERVE exists; if RedisBloom module not installed, BF commands may fail.
            try:
                # Try to create bloom filter only if not exists
                exists = await self._client.execute_command("EXISTS", self.key)
                # Reserve only if not exists (best-effort)
                await self._client.execute_command("BF.RESERVE", self.key, str(self.error_rate), str(self.capacity))
            except Exception:
                # If BF.RESERVE fails (module not installed), we still proceed using a Redis SET as fallback
                logger.warning("RedisBloom not available; will use Redis SET fallback for visited tracking.")
        return self._client

    async def add(self, url: str) -> bool:
        """
        Add URL to Bloom filter. Returns True if it was not present (i.e., newly added).
        """
        client = await self.connect()
        try:
            # Try BF.ADD
            res = await client.execute_command("BF.ADD", self.key, url)
            # BF.ADD returns 1 if added, 0 if already exists
            return bool(int(res))
        except Exception:
            # Fallback to Redis SET
            try:
                added = await client.sadd(self.key + ":set", url)
                return bool(added)
            except Exception as e:
                logger.exception("Redis fallback add failed: %s", e)
                return False

    async def exists(self, url: str) -> bool:
        client = await self.connect()
        try:
            res = await client.execute_command("BF.EXISTS", self.key, url)
            return bool(int(res))
        except Exception:
            try:
                res = await client.sismember(self.key + ":set", url)
                return bool(res)
            except Exception as e:
                logger.exception("Redis fallback exists failed: %s", e)
                return False


class LocalBloomVisited:
    def __init__(self):
        if not PYBLOOM_AVAILABLE:
            raise RuntimeError("pybloom_live not available")
        # ScalableBloomFilter grows as needed; run operations in threadpool
        self._filter = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH)

    async def add(self, url: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._add_sync, url)

    def _add_sync(self, url: str) -> bool:
        if url in self._filter:
            return False
        self._filter.add(url)
        return True

    async def exists(self, url: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: url in self._filter)


def get_visited_store():
    """
    Factory: prefer RedisBloom if REDIS_URL provided and redis available.
    """
    if settings.REDIS_URL and REDIS_AVAILABLE:
        return RedisBloomVisited(settings.REDIS_URL, settings.REDIS_BLOOM_KEY, settings.REDIS_BLOOM_CAPACITY, settings.REDIS_BLOOM_ERROR_RATE)
    elif PYBLOOM_AVAILABLE:
        logger.warning("Redis not configured or unavailable; using local Bloom filter (memory usage may grow).")
        return LocalBloomVisited()
    else:
        raise RuntimeError("No visited store available: configure Redis or install pybloom_live")
