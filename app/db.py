# app/db.py
import asyncio
import logging
from typing import Any, Dict, List, Optional
from .config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("local_search.db")

# Import async Meilisearch client
# The exact import may vary by package version; adjust if necessary.
try:
    from meilisearch_async import Client as AsyncMeiliClient  # hypothetical async client package
except Exception:
    # Fallback to meilisearch-python which may provide AsyncClient in newer versions
    try:
        from meilisearch import AsyncClient as AsyncMeiliClient
    except Exception:
        AsyncMeiliClient = None


class CircuitBreaker:
    """
    Async circuit breaker to protect Meilisearch.
    - Tracks consecutive failures; opens circuit when threshold reached.
    - While open, operations raise ConnectionError immediately.
    - After recovery timeout, circuit closes and allows attempts.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._open = False
        self._lock = asyncio.Lock()
        self._recovery_task: Optional[asyncio.Task] = None

    @property
    def open(self) -> bool:
        return self._open

    async def record_success(self):
        async with self._lock:
            self._failures = 0
            if self._open:
                logger.info("Circuit breaker: closing circuit after success.")
            self._open = False

    async def record_failure(self):
        async with self._lock:
            self._failures += 1
            logger.warning("Circuit breaker: failure count %d", self._failures)
            if self._failures >= self.failure_threshold and not self._open:
                self._open = True
                logger.error("Circuit breaker: opening circuit (threshold reached).")
                if self._recovery_task is None or self._recovery_task.done():
                    self._recovery_task = asyncio.create_task(self._attempt_recovery())

    async def _attempt_recovery(self):
        logger.info("Circuit breaker: waiting %ds before recovery attempt.", self.recovery_timeout)
        await asyncio.sleep(self.recovery_timeout)
        async with self._lock:
            self._failures = 0
            self._open = False
            logger.info("Circuit breaker: recovery window opened.")


class MeiliDB:
    def __init__(self):
        if AsyncMeiliClient is None:
            raise RuntimeError("Async Meilisearch client not available. Install an async-capable meilisearch client.")
        self.client = AsyncMeiliClient(settings.MEILI_URL, api_key=settings.MEILI_API_KEY)
        self.index_name = settings.MEILI_INDEX_NAME
        self.circuit = CircuitBreaker(settings.CB_FAILURE_THRESHOLD, settings.CB_RECOVERY_TIMEOUT)

    async def ensure_index(self, settings_payload: Dict[str, Any]):
        """
        Ensure index exists and apply settings. Uses retries to be resilient.
        """
        if self.circuit.open:
            raise ConnectionError("Circuit open; cannot ensure index now.")
        try:
            # create index if not exists
            indexes = await self.client.get_indexes()
            names = [i.uid for i in indexes]
            if self.index_name not in names:
                await self.client.create_index(self.index_name, {'primaryKey': 'id'})
            index = self.client.index(self.index_name)
            await index.update_settings(settings_payload)
            await self.circuit.record_success()
            logger.info("Meilisearch index ensured and settings applied.")
        except Exception as e:
            await self.circuit.record_failure()
            logger.exception("Failed to ensure index: %s", e)
            raise

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def index_documents(self, docs: List[Dict[str, Any]]):
        """
        Index documents using async client. Circuit breaker prevents hammering DB.
        """
        if self.circuit.open:
            raise ConnectionError("Search engine unavailable (circuit open).")
        try:
            index = self.client.index(self.index_name)
            res = await index.add_documents(docs)
            await self.circuit.record_success()
            logger.debug("Indexed %d docs", len(docs))
            return res
        except Exception as e:
            await self.circuit.record_failure()
            logger.exception("Indexing error: %s", e)
            raise

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, q: str, limit: int = 10, filters: Optional[str] = None):
        if self.circuit.open:
            raise ConnectionError("Search engine unavailable (circuit open).")
        try:
            index = self.client.index(self.index_name)
            params = {"q": q, "limit": limit}
            if filters:
                params["filter"] = filters
            res = await index.search(**params)
            await self.circuit.record_success()
            return res
        except Exception as e:
            await self.circuit.record_failure()
            logger.exception("Search error: %s", e)
            raise
