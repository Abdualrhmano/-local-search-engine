"""
Response models for API endpoints using Pydantic v2.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Status of the service")
    meilisearch: Optional[Dict[str, Any]] = Field(None, description="Meilisearch health info")
    reason: Optional[str] = Field(None, description="Reason for unhealthy status")


class CrawlResponse(BaseModel):
    """Crawl job response model."""
    status: str = Field(..., description="Status of the request")
    job_id: str = Field(..., description="Unique job identifier")
    queued_urls: int = Field(..., description="Number of URLs queued")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SearchResult(BaseModel):
    """Individual search result model."""
    id: str
    title: str
    url: str
    content: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    """Search response model with pagination."""
    status: str = Field(default="success", description="Status of the search")
    query: str = Field(..., description="Search query")
    total_results: int = Field(..., description="Total number of results")
    limit: int = Field(..., description="Results limit per page")
    offset: int = Field(..., description="Results offset")
    current_page: int = Field(..., description="Current page number")
    total_pages: int = Field(..., description="Total number of pages")
    results: List[SearchResult] = Field(..., description="Search results")


class JobStatus(BaseModel):
    """Job status details."""
    job_id: str
    status: str = Field(..., description="Job status: pending, running, completed, failed")
    urls_processed: int = Field(default=0)
    pages_crawled: int = Field(default=0)
    errors: int = Field(default=0)
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class MetricsResponse(BaseModel):
    """Metrics response model."""
    circuit_open: bool = Field(..., description="Is circuit breaker open")
    circuit_failures: int = Field(..., description="Number of circuit breaker failures")
    meili_index: str = Field(..., description="Meilisearch index name")
    total_documents: Optional[int] = Field(None)


class ErrorResponse(BaseModel):
    """Error response model."""
    status: str = Field(default="error")
    detail: str = Field(..., description="Error details")
    error_code: Optional[str] = Field(None, description="Error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DeleteIndexResponse(BaseModel):
    """Delete index response model."""
    status: str = Field(..., description="Status of deletion")
    message: str = Field(..., description="Deletion message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
