"""FR-5: Confirm Reservation

AC-5.1: POST /reservations/{id}/confirm {owner_token} → 200 with booking details.
AC-5.2: Wrong owner_token → 403.
AC-5.3: Already confirmed → 409.
AC-5.4: Non-existent reservation → 404.
AC-5.5: After confirm, seats show as 'sold'.
"""

import uuid

from verify.acceptance.conftest import (
    assert_200,
    assert_201,
    assert_403,
    assert_404,
)


def test_confirm_reservation_success(client, test_event, available_seats):
    """Reserve then confirm → 200 with booking details; seats become 'sold'."""
    seats = available_seats[:2]
    assert len(seats) >= 2, "Need at least 2 available seats for this test"

    # Reserve
    res = assert_201(
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

    # Confirm
    booking = assert_200(
        client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
    )

    assert "booking_id" in booking
    assert booking["reservation_id"] == res["reservation_id"]
    assert booking["status"] == "confirmed"
    assert "seats" in booking
    assert len(booking["seats"]) == 2
    for s in booking["seats"]:
        assert "seat_id" in s
        assert "section" in s
        assert "row" in s
        assert "seat_label" in s

    # Verify seats are now sold
    r = client.get(f"/events/{test_event['event_id']}/seats")
    seat_map = assert_200(r)
    seat_statuses = {
        s["seat_id"]: s["status"] for s in seat_map["seats"] if s["seat_id"] in res["seat_ids"]
    }
    for seat_id in res["seat_ids"]:
        assert (
            seat_statuses.get(seat_id) == "sold"
        ), f"Seat {seat_id} expected 'sold', got '{seat_statuses.get(seat_id)}'"


def test_confirm_wrong_owner_token(client, test_event, available_seats):
    """Confirm with wrong owner_token → 403 (fencing)."""
    seats = available_seats[:1]
    assert len(seats) >= 1, "Need at least 1 available seat"

    res = assert_201(
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

    assert_403(
        client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": str(uuid.uuid4())},  # wrong token
        )
    )


def test_confirm_already_confirmed(client, test_event, available_seats):
    """Confirm twice → 409 on second attempt."""
    seats = available_seats[:1]
    assert len(seats) >= 1, "Need at least 1 available seat"

    res = assert_201(
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

    # First confirm succeeds
    assert_200(
        client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
    )

    # Second confirm fails
    r = client.post(
        f"/reservations/{res['reservation_id']}/confirm",
        json={"owner_token": res["owner_token"]},
    )
    assert r.status_code == 409, f"Expected 409 on double confirm, got {r.status_code}: {r.text}"


def test_confirm_nonexistent_reservation(client):
    """Confirm non-existent reservation → 404."""
    r = client.post(
        "/reservations/00000000-0000-0000-0000-000000000000/confirm",
        json={"owner_token": str(uuid.uuid4())},
    )
    assert_404(r)
