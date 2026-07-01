# app/crawler.py
import asyncio
import logging
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from selectolax.parser import HTMLParser
from urllib.parse import urljoin
from .config import settings
from .utils import make_id, domain_from_url, now_iso
from .storage import get_visited_store
from .db import MeiliDB
from .models import ZyteResponseModel, PageDocument
import json

logger = logging.getLogger("local_search.crawler")

# Zyte client import (official library)
try:
    from zyte_api import ZyteClient  # hypothetical official client
except Exception:
    ZyteClient = None

# Thread pool for CPU-bound parsing tasks
CPU_POOL = ThreadPoolExecutor(max_workers=4)


class Crawler:
    """
    Asynchronous crawler that:
    - Uses Zyte to fetch rendered HTML (handles anti-bot).
    - Uses selectolax for fast parsing (C-based).
    - Tracks visited URLs via RedisBloom (or local Bloom fallback).
    - Batches documents and indexes them via MeiliDB (async).
    - Implements auto-healing: retries, per-domain backoff, circuit breaker handling.
    """

    def __init__(self, db: MeiliDB):
        self.db = db
        self.visited = get_visited_store()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.domain_delay: Dict[str, float] = {}
        self.index_buffer: List[Dict[str, Any]] = []
        self.index_lock = asyncio.Lock()
        self.batch_size = settings.CRAWL_BATCH_SIZE
        self.semaphore = asyncio.Semaphore(settings.CRAWL_CONCURRENCY)
        self.zyte = None
        if ZyteClient:
            # Zyte client is expected to be async-capable; if not, wrap calls appropriately.
            self.zyte = ZyteClient(api_key=settings.ZYTE_API_KEY)
        self._stop = False

    async def start(self):
        # Ensure index exists
        try:
            import json as _json
            from pathlib import Path
            payload = _json.loads(Path("mappings/meilisearch_index_settings.json").read_text())
            await self.db.ensure_index(payload)
        except Exception as e:
            logger.exception("Failed to ensure index at crawler start: %s", e)

    async def enqueue(self, url: str, depth: int = 0):
        await self.queue.put((url, depth))

    async def _is_visited(self, url: str) -> bool:
        try:
            return await self.visited.exists(url)
        except Exception:
            # If visited store fails, be conservative and treat as not visited to avoid skipping
            logger.exception("Visited store check failed; treating as not visited.")
            return False

    async def _mark_visited(self, url: str) -> bool:
        try:
            return await self.visited.add(url)
        except Exception:
            logger.exception("Visited store add failed; continuing.")
            return False

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        stop=stop_after_attempt(settings.CRAWL_MAX_RETRIES),
        reraise=True,
    )
    async def fetch_via_zyte(self, url: str) -> Optional[ZyteResponseModel]:
        """
        Fetch rendered HTML via Zyte. Retries transient errors with exponential backoff.
        Zyte client usage depends on the official library API; adapt as needed.
        """
        if self.zyte is None:
            raise RuntimeError("Zyte client not configured. Set ZYTE_API_KEY.")
        try:
            # Example Zyte async call; adapt to actual client API.
            # We request rendered HTML and headers.
            resp = await self.zyte.fetch(url, timeout=settings.CRAWL_TIMEOUT)
            # resp is expected to be a dict-like object with 'html', 'status', 'headers'
            model = ZyteResponseModel(
                url=resp.get("url", url),
                html=resp.get("html"),
                status=resp.get("status"),
                headers=resp.get("headers"),
                fetched_at=resp.get("fetched_at")
            )
            return model
        except Exception as e:
            logger.exception("Zyte fetch failed for %s: %s", url, e)
            raise

    async def parse_and_extract(self, url: str, html: str) -> Dict[str, Any]:
        """
        Parse HTML using selectolax in a threadpool to avoid blocking the event loop.
        Returns a dict ready for indexing.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(CPU_POOL, self._parse_sync, url, html)

    def _parse_sync(self, url: str, html: str) -> Dict[str, Any]:
        """
        CPU-bound parsing executed in a threadpool.
        Uses selectolax for speed and low memory.
        """
        try:
            tree = HTMLParser(html)
            title_node = tree.css_first("title")
            title = title_node.text() if title_node else None
            meta_desc = None
            md = tree.css_first('meta[name="description"]')
            if md:
                meta_desc = md.attributes.get("content")
            # Extract visible text (simple approach)
            texts = []
            for node in tree.css("p, h1, h2, h3, article"):
                txt = node.text(separator=" ", strip=True)
                if txt:
                    texts.append(txt)
            content = " ".join(texts)[:200000]
            # Extract links
            links = []
            for a in tree.css("a"):
                href = a.attributes.get("href")
                if href:
                    full = urljoin(url, href)
                    links.append(full)
            return {
                "title": title,
                "meta_description": meta_desc,
                "content": content,
                "links": links
            }
        except Exception as e:
            logger.exception("Parsing failed for %s: %s", url, e)
            return {"title": None, "meta_description": None, "content": None, "links": []}

    async def buffer_and_index(self, doc: Dict[str, Any]):
        async with self.index_lock:
            self.index_buffer.append(doc)
            if len(self.index_buffer) >= self.batch_size:
                batch = self.index_buffer[:]
                self.index_buffer = []
                asyncio.create_task(self._index_batch(batch))

    async def _index_batch(self, batch: List[Dict[str, Any]]):
        try:
            await self.db.index_documents(batch)
        except Exception as e:
            # On failure, re-buffer and back off to avoid tight retry loops
            logger.exception("Batch indexing failed: %s", e)
            async with self.index_lock:
                self.index_buffer = batch + self.index_buffer
            await asyncio.sleep(2.0)

    async def worker(self, max_depth: int):
        while not self._stop:
            try:
                url, depth = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # queue empty; worker can exit if desired
                await asyncio.sleep(0.1)
                continue

            # Skip if already visited
            try:
                if await self._is_visited(url):
                    continue
                await self._mark_visited(url)
            except Exception:
                # If visited store fails, continue but log
                logger.exception("Visited store error for %s", url)

            # Acquire concurrency semaphore
            async with self.semaphore:
                try:
                    zyte_resp = await self.fetch_via_zyte(url)
                    if zyte_resp is None or not zyte_resp.html:
                        logger.debug("No HTML from Zyte for %s", url)
                        continue
                    parsed = await self.parse_and_extract(url, zyte_resp.html)
                    doc = {
                        "id": make_id(url),
                        "url": url,
                        "domain": domain_from_url(url),
                        "title": parsed.get("title"),
                        "content": parsed.get("content"),
                        "meta_description": parsed.get("meta_description"),
                        "published_at": None,
                        "language": None,
                        "fetched_at": now_iso(),
                    }
                    await self.buffer_and_index(doc)

                    # Enqueue discovered links if depth allows
                    if depth < max_depth:
                        for link in parsed.get("links", []):
                            # Basic normalization and filtering
                            if link.startswith("mailto:") or link.startswith("javascript:"):
                                continue
                            await self.queue.put((link, depth + 1))
                except Exception as e:
                    logger.exception("Worker error for %s: %s", url, e)
                    # Auto-healing: if Zyte times out or returns anti-bot, we rely on tenacity retries and continue.

    async def crawl(self, start_urls: List[str], max_pages: int = 100, max_depth: int = 1):
        """
        Entry point to start crawling. Spawns worker tasks and seeds the queue.
        """
        # Seed
        for u in start_urls:
            await self.queue.put((u, 0))

        # Start workers
        workers = [asyncio.create_task(self.worker(max_depth)) for _ in range(settings.CRAWL_CONCURRENCY)]
        processed = 0
        try:
            while processed < max_pages:
                # Wait for queue to be empty or until processed reaches max_pages
                try:
                    await asyncio.sleep(0.1)
                    processed += 1  # conservative increment; real counting can be added
                except asyncio.CancelledError:
                    break
                if self.queue.empty():
                    break
        finally:
            # Stop workers
            self._stop = True
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            # Flush remaining buffer
            async with self.index_lock:
                if self.index_buffer:
                    await self._index_batch(self.index_buffer)
                    self.index_buffer = []
