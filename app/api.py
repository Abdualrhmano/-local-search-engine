# app/api.py
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from .models import CrawlRequest
from .tasks import run_crawl_job
from .db import MeiliDB
from .config import settings
import asyncio
import json
from pathlib import Path

logger = logging.getLogger("local_search.api")

app = FastAPI(title="Local Search Engine (Zyte + Meilisearch)", version="1.0.0")

db = MeiliDB()


@app.on_event("startup")
async def startup_event():
    # Ensure index exists at startup; if Meilisearch is down, circuit breaker will protect runtime calls.
    try:
        settings_payload = json.loads(Path("mappings/meilisearch_index_settings.json").read_text())
        await db.ensure_index(settings_payload)
    except Exception as e:
        logger.exception("Startup: failed to ensure index: %s", e)


@app.get("/health")
async def health():
    """
    Health endpoint. Returns DB circuit state and basic connectivity.
    """
    if db.circuit.open:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "reason": "search_engine_unavailable"})
    try:
        # Async client health check (method name may vary)
        res = await db.client.health()
        return {"status": "ok", "meilisearch": res}
    except Exception as e:
        logger.exception("Health check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "unhealthy", "reason": "meilisearch_error"})


@app.post("/crawl", status_code=202)
async def crawl(req: CrawlRequest, background_tasks: BackgroundTasks):
    """
    Start a crawl job in background. Pydantic v2 validates input.
    """
    urls = [str(u) for u in req.urls]
    max_pages = int(req.max_pages)
    background_tasks.add_task(run_crawl_job, urls, req.depth, max_pages)
    return {"status": "accepted", "queued_urls": len(urls)}


@app.get("/search")
async def search(q: str, limit: int = 10, filters: str = None):
    """
    Search endpoint. Uses MeiliDB.search wrapper which includes retries and circuit breaker.
    """
    try:
        res = await db.search(q, limit=limit, filters=filters)
        return res
    except ConnectionError as ce:
        logger.error("Search failed due to DB unavailability: %s", ce)
        raise HTTPException(status_code=503, detail="Search engine unavailable. Try again later.")
    except Exception as e:
        logger.exception("Search error: %s", e)
        raise HTTPException(status_code=500, detail="Internal search error.")


@app.get("/metrics")
async def metrics():
    return {
        "circuit_open": db.circuit.open,
        "circuit_failures": db.circuit._failures,
        "meili_index": settings.MEILI_INDEX_NAME,
    }
