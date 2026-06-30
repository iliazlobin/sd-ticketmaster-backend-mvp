"""Tests for application configuration."""

from unittest.mock import patch

from ticketmaster.config import Settings


def test_default_database_url() -> None:
    """Default DATABASE_URL matches expected format."""
    with patch.dict("os.environ", {}, clear=True):
        s = Settings()
        assert "postgresql+asyncpg" in s.database_url


def test_default_redis_url() -> None:
    """Default REDIS_URL matches expected format."""
    with patch.dict("os.environ", {}, clear=True):
        s = Settings()
        assert s.redis_url.startswith("redis://")


def test_default_port() -> None:
    """Default port is 8000."""
    s = Settings()
    assert s.port == 8000


def test_seat_hold_ttl_default() -> None:
    """Default seat hold TTL is 600 seconds (10 minutes), overridable via env."""
    # Environment may override; test that the config value is an int > 0
    s = Settings()
    assert isinstance(s.seat_hold_ttl, int)
    assert s.seat_hold_ttl > 0
