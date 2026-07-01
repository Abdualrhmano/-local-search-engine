# app/tasks.py
import asyncio
import logging
from .crawler import Crawler
from .db import MeiliDB

logger = logging.getLogger("local_search.tasks")


async def run_crawl_job(urls, depth=1, max_pages=100):
    db = MeiliDB()
    crawler = Crawler(db)
    await crawler.start()
    try:
        await crawler.crawl(start_urls=urls, max_pages=max_pages, max_depth=depth)
    except Exception as e:
        logger.exception("Crawl job failed: %s", e)
    finally:
        # ensure any remaining docs are flushed
        try:
            async with crawler.index_lock:
                if crawler.index_buffer:
                    await crawler._index_batch(crawler.index_buffer)
        except Exception:
            logger.exception("Final flush failed.")
