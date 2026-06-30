from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, driven by environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Database
    database_url: str = "postgresql+asyncpg://ticketmaster:ticketmaster@localhost:5432/ticketmaster"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Seat hold TTL in seconds (10 minutes)
    seat_hold_ttl: int = 600


settings = Settings()
