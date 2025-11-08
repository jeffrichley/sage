"""Application settings loaded from environment variables and config files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, PositiveInt, SecretStr
from pydantic.networks import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from sage.config import CONFIG_ROOT


class ServiceRateLimit(BaseModel):
    """Rate limit configuration for an external service."""

    requests_per_day: Optional[PositiveInt] = None
    requests_per_hour: Optional[PositiveInt] = None
    requests_per_minute: Optional[PositiveInt] = None
    tokens_per_minute: Optional[PositiveInt] = None
    burst: Optional[PositiveInt] = None

    model_config = ConfigDict(extra="forbid")


class RateLimitConfig(BaseModel):
    """Top-level configuration for all service rate limits."""

    services: Dict[str, ServiceRateLimit] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def _load_rate_limits(rate_limit_path: Path) -> RateLimitConfig:
    if not rate_limit_path.exists():
        return RateLimitConfig()

    raw_data = yaml.safe_load(rate_limit_path.read_text(encoding="utf-8")) or {}

    services: Dict[str, ServiceRateLimit] = {}
    for service_name, config in raw_data.get("services", {}).items():
        services[service_name] = ServiceRateLimit(**config)
    return RateLimitConfig(services=services)


class Settings(BaseSettings):
    """Primary application settings for the Sage CLI."""

    database_url: PostgresDsn = Field(alias="DATABASE_URL")
    mem0_api_key: Optional[SecretStr] = Field(default=None, alias="MEM0_API_KEY")
    openai_api_key: Optional[SecretStr] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[SecretStr] = Field(default=None, alias="ANTHROPIC_API_KEY")
    langfuse_public_key: Optional[SecretStr] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[SecretStr] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: Optional[HttpUrl] = Field(default=None, alias="LANGFUSE_HOST")

    max_summary_words: PositiveInt = Field(default=300, alias="MAX_SUMMARY_WORDS")
    keep_timestamps: bool = Field(default=True, alias="KEEP_TIMESTAMPS")
    enable_summarization: bool = Field(default=True, alias="ENABLE_SUMMARIZATION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    rate_limits: RateLimitConfig = Field(default_factory=lambda: _load_rate_limits(CONFIG_ROOT / "rate_limits.yaml"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""

    return Settings()


__all__ = ["Settings", "ServiceRateLimit", "RateLimitConfig", "get_settings"]

