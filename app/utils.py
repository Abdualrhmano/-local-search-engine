# app/utils.py
import hashlib
from urllib.parse import urlparse
from datetime import datetime
import logging

logger = logging.getLogger("local_search.utils")


def make_id(url: str) -> str:
    """Deterministic ID for a URL (used as primary key in Meilisearch)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"
