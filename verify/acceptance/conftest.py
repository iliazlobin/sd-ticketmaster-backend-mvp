"""Shared fixtures and helpers for the black-box acceptance suite.

These tests do NOT import `src.ticketmaster`. They talk to the running system
via HTTP at API_BASE_URL.

Seed requirement: the database must contain at least one event with at least
3 available seats before running these tests. The e2e-verify loop or a pre-seed
script is responsible for this.
"""

import os
import uuid

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def client():
    """Session-scoped httpx client for the entire acceptance run."""
    with httpx.Client(base_url=API_BASE_URL, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def test_event(client):
    """Find an event with available seats. Assumes pre-seeded test data."""
    r = client.get("/events", params={"page": 1})
    assert r.status_code == 200, f"GET /events failed: {r.status_code} {r.text}"
    data = r.json()
    events = data.get("events", data if isinstance(data, list) else [])
    assert len(events) > 0, (
        "No events found. Seed the database with at least one event "
        "before running acceptance tests."
    )
    # Prefer an event with available seats
    for ev in events:
        if ev.get("available_seats", 0) > 0:
            return ev
    return events[0]


@pytest.fixture(scope="session")
def test_seats(client, test_event):
    """All seats for the test event."""
    event_id = test_event["event_id"]
    r = client.get(f"/events/{event_id}/seats")
    assert r.status_code == 200, f"GET /events/{event_id}/seats failed: {r.status_code}"
    return r.json()["seats"]


@pytest.fixture
def available_seats(client, test_event):
    """Fresh list of available seats (re-queried each test)."""
    event_id = test_event["event_id"]
    r = client.get(f"/events/{event_id}/seats")
    assert r.status_code == 200
    seats = r.json()["seats"]
    avail = [s for s in seats if s["status"] == "available"]
    if not avail:
        pytest.skip("No available seats — test data exhausted")
    return avail


def _random_key():
    return str(uuid.uuid4())


# ---- Assertion helpers ----


def assert_200(r):
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    return r.json()


def assert_201(r):
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    return r.json()


def assert_404(r):
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def assert_409(r):
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    return r.json()


def assert_403(r):
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def assert_410(r):
    assert r.status_code == 410, f"Expected 410, got {r.status_code}: {r.text}"


def assert_422(r):
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    return r.json()
