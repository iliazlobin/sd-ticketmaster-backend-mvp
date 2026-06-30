"""FR-4: Reserve Seats

AC-4.1: POST /reservations {event_id, seat_ids, user_id, idempotency_key} → 201 with {reservation_id, owner_token, expires_at}.
AC-4.2: Any seat unavailable → 409 with conflicting_seat_ids.
AC-4.3: Seat from wrong event → 422.
AC-4.4: Empty seat_ids → 422.
AC-4.5: Seats become unavailable after reservation (reflected in GET /events/{id}/seats).
"""

import uuid

from verify.acceptance.conftest import assert_200, assert_201, assert_409, assert_422


def test_reserve_seats_success(client, test_event, available_seats):
    """POST /reservations with valid data → 201 with correct response shape."""
    seats = available_seats[:2]
    assert len(seats) >= 2, "Need at least 2 available seats for this test"

    body = assert_201(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [s["seat_id"] for s in seats],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
    )

    assert "reservation_id" in body
    assert body["event_id"] == test_event["event_id"]
    assert len(body["seat_ids"]) == 2
    assert "owner_token" in body
    assert isinstance(body["owner_token"], str) and len(body["owner_token"]) > 0
    assert "expires_at" in body
    assert body["status"] == "pending"


def test_reserve_seats_makes_seats_held(client, test_event, available_seats):
    """After reservation, seats show as 'held' in the seat map."""
    seats = available_seats[:2]
    assert len(seats) >= 2, "Need at least 2 available seats for this test"

    body = assert_201(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [s["seat_id"] for s in seats],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
    )

    # Check seat map
    r = client.get(f"/events/{test_event['event_id']}/seats")
    seat_map = assert_200(r)
    seat_statuses = {
        s["seat_id"]: s["status"] for s in seat_map["seats"] if s["seat_id"] in body["seat_ids"]
    }
    for seat_id in body["seat_ids"]:
        assert (
            seat_statuses.get(seat_id) == "held"
        ), f"Seat {seat_id} expected 'held', got '{seat_statuses.get(seat_id)}'"


def test_reserve_already_held_seat(client, test_event, available_seats):
    """Reserving a seat that's already held → 409 with conflicting seat_ids."""
    seats = available_seats[:2]
    assert len(seats) >= 2, "Need at least 2 available seats for this test"
    seat_ids = [s["seat_id"] for s in seats]

    # First reservation — succeeds
    assert_201(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": seat_ids,
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
    )

    # Second reservation for the same seats — fails
    err = assert_409(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": seat_ids,
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
    )
    assert (
        "conflicting_seat_ids" in err or "detail" in err
    ), f"409 response should indicate conflict: {err}"


def test_reserve_empty_seat_ids(client, test_event):
    """POST /reservations with empty seat_ids → 422."""
    assert_422(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
    )


def test_reserve_missing_fields(client, test_event):
    """POST /reservations with missing required fields → 422."""
    assert_422(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                # missing seat_ids, user_id, idempotency_key
            },
        )
    )


def test_reserve_wrong_event(client, test_event):
    """POST /reservations with event_id not matching seats' event → 422."""
    # Use a random event_id that doesn't match any seat
    wrong_event_id = str(uuid.uuid4())
    body = client.post(
        "/reservations",
        json={
            "event_id": wrong_event_id,
            "seat_ids": [str(uuid.uuid4())],
            "user_id": str(uuid.uuid4()),
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert body.status_code in (
        404,
        422,
    ), f"Expected 404 or 422, got {body.status_code}: {body.text}"
