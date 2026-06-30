"""Functional tests — in-process endpoint scenarios.

Tests idempotency, ordering, pagination, ownership/auth, and validation/error paths.
Uses httpx.AsyncClient against the running FastAPI app.
"""

import os
import uuid

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30) as c:
        yield c


@pytest.fixture
async def test_event(client):
    r = await client.get("/events", params={"page": 1})
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) > 0
    for ev in events:
        if ev.get("available_seats", 0) > 0:
            return ev
    return events[0]


@pytest.fixture
async def available_seats(client, test_event):
    event_id = test_event["event_id"]
    r = await client.get(f"/events/{event_id}/seats")
    assert r.status_code == 200
    seats = r.json()["seats"]
    avail = [s for s in seats if s["status"] == "available"]
    if not avail:
        pytest.skip("No available seats")
    return avail


class TestPagination:
    """Pagination and ordering tests for GET /events."""

    async def test_page_1_returns_first_page(self, client):
        r = await client.get("/events", params={"page": 1})
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert "total" in body
        assert "events" in body

    async def test_high_page_returns_empty(self, client):
        r = await client.get("/events", params={"page": 99999})
        assert r.status_code == 200
        body = r.json()
        assert body["events"] == []

    async def test_events_ordered_by_date(self, client):
        r = await client.get("/events", params={"page": 1})
        assert r.status_code == 200
        events = r.json()["events"]
        if len(events) >= 2:
            dates = [e["event_date"] for e in events]
            assert dates == sorted(dates), f"Events not sorted by date: {dates}"


class TestValidationErrors:
    """Validation and error path tests."""

    async def test_invalid_page_param_returns_422(self, client):
        r = await client.get("/events", params={"page": "abc"})
        assert r.status_code == 422

    async def test_missing_search_query_returns_422(self, client):
        r = await client.get("/search")
        assert r.status_code == 422

    async def test_empty_search_query_returns_422(self, client):
        r = await client.get("/search", params={"q": ""})
        assert r.status_code == 422

    async def test_empty_seat_ids_returns_422(self, client, test_event):
        r = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 422

    async def test_missing_required_fields_returns_422(self, client, test_event):
        r = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
            },
        )
        assert r.status_code == 422

    async def test_nonexistent_event_seat_map_returns_404(self, client):
        r = await client.get(f"/events/{uuid.uuid4()}/seats")
        assert r.status_code == 404

    async def test_nonexistent_booking_returns_404(self, client):
        r = await client.get(f"/bookings/{uuid.uuid4()}")
        assert r.status_code == 404


class TestIdempotency:
    """Idempotency key tests for POST /reservations."""

    async def test_same_key_returns_200_with_same_reservation(
        self, client, test_event, available_seats
    ):
        seats = available_seats[:2]
        assert len(seats) >= 2
        idem_key = str(uuid.uuid4())
        payload = {
            "event_id": test_event["event_id"],
            "seat_ids": [s["seat_id"] for s in seats],
            "user_id": str(uuid.uuid4()),
            "idempotency_key": idem_key,
        }

        r1 = await client.post("/reservations", json=payload)
        assert r1.status_code == 201
        res1 = r1.json()

        r2 = await client.post("/reservations", json=payload)
        assert r2.status_code == 200
        res2 = r2.json()

        assert res2["reservation_id"] == res1["reservation_id"]
        assert res2["owner_token"] == res1["owner_token"]
        assert res2["status"] == "pending"

    async def test_different_seats_same_key_returns_422(self, client, test_event, available_seats):
        seats = available_seats[:3]
        assert len(seats) >= 3
        idem_key = str(uuid.uuid4())

        r1 = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[0]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": idem_key,
            },
        )
        assert r1.status_code == 201

        r2 = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[1]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": idem_key,
            },
        )
        assert r2.status_code == 422


class TestOwnershipAuth:
    """Ownership / authorization tests for confirm endpoint."""

    async def test_wrong_owner_token_returns_403(self, client, test_event, available_seats):
        seats = available_seats[:1]
        assert len(seats) >= 1

        r = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[0]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 201
        res = r.json()

        r2 = await client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": str(uuid.uuid4())},
        )
        assert r2.status_code == 403

    async def test_double_confirm_returns_409(self, client, test_event, available_seats):
        seats = available_seats[:1]
        assert len(seats) >= 1

        r = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[0]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 201
        res = r.json()

        # First confirm
        r2 = await client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
        assert r2.status_code == 200

        # Second confirm
        r3 = await client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
        assert r3.status_code == 409


class TestReservationLifecycle:
    """Full reservation lifecycle tests."""

    async def test_reserve_confirm_get_booking_flow(self, client, test_event, available_seats):
        seats = available_seats[:2]
        assert len(seats) >= 2

        # Reserve
        r = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [s["seat_id"] for s in seats],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 201
        res = r.json()
        assert res["status"] == "pending"
        assert "expires_at" in res
        assert "owner_token" in res

        # Verify seats are held
        r_seats = await client.get(f"/events/{test_event['event_id']}/seats")
        assert r_seats.status_code == 200
        seat_map = {s["seat_id"]: s["status"] for s in r_seats.json()["seats"]}
        for sid in res["seat_ids"]:
            assert seat_map[sid] == "held"

        # Confirm
        r2 = await client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
        assert r2.status_code == 200
        booking = r2.json()
        assert booking["status"] == "confirmed"
        assert len(booking["seats"]) == 2
        assert "booking_id" in booking

        # Get booking
        r3 = await client.get(f"/bookings/{booking['booking_id']}")
        assert r3.status_code == 200
        assert r3.json()["booking_id"] == booking["booking_id"]

        # Verify seats are now sold
        r_seats2 = await client.get(f"/events/{test_event['event_id']}/seats")
        seat_map2 = {s["seat_id"]: s["status"] for s in r_seats2.json()["seats"]}
        for sid in res["seat_ids"]:
            assert seat_map2[sid] == "sold"


class TestConflictDetection:
    """Conflict detection tests."""

    async def test_reserve_already_held_returns_409_with_conflicting_ids(
        self, client, test_event, available_seats
    ):
        seats = available_seats[:2]
        assert len(seats) >= 2

        # First reservation
        r1 = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [s["seat_id"] for s in seats],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r1.status_code == 201

        # Try to reserve same seats
        r2 = await client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [s["seat_id"] for s in seats],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r2.status_code == 409
        body = r2.json()
        detail = body.get("detail", {})
        if isinstance(detail, dict):
            assert "conflicting_seat_ids" in detail or "detail" in detail
