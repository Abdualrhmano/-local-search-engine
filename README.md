# Local Search Engine

A local, self-hosted search system that crawls web pages, extracts searchable content, and indexes documents in Meilisearch for fast full-text retrieval.

The backend is implemented with FastAPI and an asynchronous crawler pipeline. The repository also includes a lightweight frontend for query input and result rendering.

## Project Purpose

This project provides a focused search stack for building a local index of crawled pages:

- Crawl seed URLs (with controlled depth and page limits)
- Parse and normalize page content
- Store documents in a Meilisearch index
- Expose search and health endpoints over HTTP

## Architecture Overview

### Backend (`app/`)

- **API layer**: `app/api.py`
  - `GET /health`
  - `POST /crawl`
  - `GET /search`
  - `GET /metrics`
- **Crawler orchestration**: `app/tasks.py`, `app/crawler.py`
- **Search/index adapter**: `app/db.py` (async Meilisearch client + retry + circuit breaker)
- **Visited URL store**: `app/storage.py`
  - Primary: Redis + RedisBloom commands
  - Fallback: local Bloom filter (`pybloom_live`) when available
- **Configuration**: `app/config.py` via environment variables and `.env`
- **Data models**: `app/models.py` (crawl request, page document, Zyte response)

### Frontend (`frontend/`)

Static UI files:

- `index.html`
- `styles.css`
- `app.js`

The frontend calls `/search` directly on the same origin and renders hits (`title`, `url`, snippet from `content`).

### Index Settings / Mapping

The repository includes a Meilisearch settings JSON in the `mappings ` directory:

- `mappings /meilisearchـــindexـــsettings.json`

This file defines searchable/displayed/filterable attributes and ranking rules.

## Key Capabilities

- Async crawl workers with configurable concurrency
- Retry logic for crawling and indexing (`tenacity` exponential backoff)
- Circuit breaker around Meilisearch operations
- Content extraction using `selectolax`
- URL deduplication through Bloom-filter-style visited tracking
- Background crawl execution via FastAPI `BackgroundTasks`
- Query endpoint with optional filters passthrough to Meilisearch

## Prerequisites

- Python 3.10+
- Running Meilisearch instance
- (Recommended) Redis server with RedisBloom module for visited-URL tracking
- (For crawling) Zyte API key and compatible Zyte client behavior

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Environment variables are defined in `app/config.py` (loaded from `.env` if present).

### Required / practically required

- `MEILI_URL` (default: `http://127.0.0.1:7700`)
- `MEILI_API_KEY` (optional unless your Meilisearch instance requires it)
- `ZYTE_API_KEY` (required to successfully fetch pages in crawler)

### Optional

- `MEILI_INDEX_NAME` (default: `local_pages`)
- `REDIS_URL` (enables Redis-based visited tracking)
- `REDIS_BLOOM_KEY` (default: `visited_bloom`)
- `REDIS_BLOOM_ERROR_RATE` (default: `0.001`)
- `REDIS_BLOOM_CAPACITY` (default: `10000000`)
- `CRAWL_CONCURRENCY` (default: `8`)
- `CRAWL_TIMEOUT` (default: `30`)
- `CRAWL_USER_AGENT` (default: `LocalSearchBot/2.0 (+https://example.local)`)
- `CRAWL_DEFAULT_DELAY` (default: `0.2`)
- `CRAWL_MAX_RETRIES` (default: `4`)
- `CRAWL_BATCH_SIZE` (default: `25`)
- `CB_FAILURE_THRESHOLD` (default: `5`)
- `CB_RECOVERY_TIMEOUT` (default: `30`)
- `API_HOST` (default: `0.0.0.0`)
- `API_PORT` (default: `8000`)
- `ZYTE_PROJECT` (defined in settings model)

## Start the Service

Run with the packaged entrypoint:

```bash
python -m app.main
```

Or run directly with Uvicorn:

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

## API Usage

### Health check

```bash
curl "http://127.0.0.1:8000/health"
```

### Queue a crawl job

```bash
curl -X POST "http://127.0.0.1:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "depth": 1,
    "max_pages": 100
  }'
```

### Search

```bash
curl "http://127.0.0.1:8000/search?q=example&limit=10"
```

With filter expression passthrough:

```bash
curl "http://127.0.0.1:8000/search?q=example&limit=10&filters=domain%20%3D%20example.com"
```

### Metrics

```bash
curl "http://127.0.0.1:8000/metrics"
```

## Frontend

The frontend files are static and not mounted by the FastAPI app in the current codebase.

If you serve `frontend/` from a web server, ensure requests to `/search` are routed to the backend API origin expected by `frontend/app.js`.

## Directory Structure

```text
.
├── app/
│   ├── api.py
│   ├── config.py
│   ├── crawler.py
│   ├── db.py
│   ├── main.py
│   ├── models.py
│   ├── responses.py
│   ├── storage.py
│   ├── tasks.py
│   └── utils.py
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── mappings /
│   └── meilisearchـــindexـــsettings.json
├── requirements.txt
└── README.md
```

## Operational Notes

- The startup and crawler code currently attempt to read:
  - `mappings/meilisearch_index_settings.json`
- The repository currently stores the mapping file under a different literal path/name:
  - `mappings /meilisearchـــindexـــsettings.json`

Aligning these paths is necessary for automatic index-settings loading to work as written.

- `app/responses.py` defines rich response models, but API routes currently return plain dictionaries/JSON responses directly.

## Security Considerations

- Keep API keys (for Zyte and Meilisearch) in environment variables or `.env`, never hardcoded.
- Restrict network exposure of Meilisearch and Redis in production environments.
- Validate and control crawl targets to avoid abuse (large scans, sensitive/internal targets).
- Review crawler behavior and legal/compliance requirements before crawling external domains.

## Contributing

1. Fork the repository and create a feature branch.
2. Keep changes focused and minimal.
3. Verify behavior locally before opening a pull request.
4. Submit a clear PR describing the problem and solution.

## License

No license file is currently present in this repository. All rights status should be clarified by the repository owner.
