"""Tests for the FastAPI app creation and health check."""

from fastapi import FastAPI

from ticketmaster.main import create_app


def test_create_app_returns_fastapi() -> None:
    """create_app() returns a FastAPI instance with correct metadata."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Ticketmaster MVP"
    assert app.version == "0.1.0"


def test_healthz_route_exists() -> None:
    """GET /healthz route is registered on the app."""
    app = create_app()
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/healthz" in routes
