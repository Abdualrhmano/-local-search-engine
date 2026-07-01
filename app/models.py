# app/models.py
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime


class CrawlRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., description="Seed URLs to crawl")
    depth: int = Field(1, ge=0, le=3, description="Crawl depth (0 = only seeds)")
    max_pages: int = Field(100, ge=1, description="Maximum pages to crawl")


class ZyteResponseModel(BaseModel):
    """
    Minimal model for Zyte responses we expect.
    Adjust fields to match the Zyte API response shape in your account.
    """
    url: HttpUrl
    html: Optional[str]
    status: Optional[int]
    headers: Optional[dict]
    fetched_at: Optional[datetime]


class PageDocument(BaseModel):
    id: str
    url: HttpUrl
    domain: str
    title: Optional[str]
    content: Optional[str]
    meta_description: Optional[str]
    published_at: Optional[datetime]
    language: Optional[str]
    fetched_at: datetime
