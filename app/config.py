# app/config.py
from pydantic import BaseSettings, AnyHttpUrl, Field
from typing import Optional


class Settings(BaseSettings):
    # Zyte
    ZYTE_API_KEY: Optional[str] = Field(None, env="ZYTE_API_KEY")
    ZYTE_PROJECT: Optional[str] = Field(None, env="ZYTE_PROJECT")

    # Meilisearch (async client)
    MEILI_URL: AnyHttpUrl = Field("http://127.0.0.1:7700", env="MEILI_URL")
    MEILI_API_KEY: Optional[str] = Field(None, env="MEILI_API_KEY")
    MEILI_INDEX_NAME: str = Field("local_pages", env="MEILI_INDEX_NAME")

    # Redis (for Bloom filter / visited set)
    REDIS_URL: Optional[str] = Field(None, env="REDIS_URL")  # e.g., redis://localhost:6379/0
    REDIS_BLOOM_KEY: str = Field("visited_bloom", env="REDIS_BLOOM_KEY")
    REDIS_BLOOM_ERROR_RATE: float = Field(0.001, env="REDIS_BLOOM_ERROR_RATE")
    REDIS_BLOOM_CAPACITY: int = Field(10_000_000, env="REDIS_BLOOM_CAPACITY")

    # Crawler
    CRAWL_CONCURRENCY: int = Field(8, env="CRAWL_CONCURRENCY")
    CRAWL_TIMEOUT: int = Field(30, env="CRAWL_TIMEOUT")
    CRAWL_USER_AGENT: str = Field("LocalSearchBot/2.0 (+https://example.local)", env="CRAWL_USER_AGENT")
    CRAWL_DEFAULT_DELAY: float = Field(0.2, env="CRAWL_DEFAULT_DELAY")
    CRAWL_MAX_RETRIES: int = Field(4, env="CRAWL_MAX_RETRIES")
    CRAWL_BATCH_SIZE: int = Field(25, env="CRAWL_BATCH_SIZE")

    # Circuit breaker
    CB_FAILURE_THRESHOLD: int = Field(5, env="CB_FAILURE_THRESHOLD")
    CB_RECOVERY_TIMEOUT: int = Field(30, env="CB_RECOVERY_TIMEOUT")

    # API
    API_HOST: str = Field("0.0.0.0", env="API_HOST")
    API_PORT: int = Field(8000, env="API_PORT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
