"""FR-6: Get Booking

AC-6.1: GET /bookings/{booking_id} → 200 with booking + seat details.
AC-6.2: Non-existent booking → 404.
"""

import uuid

from verify.acceptance.conftest import assert_200, assert_201, assert_404


def test_get_booking_success(client, test_event, available_seats):
    """Reserve + confirm → GET /bookings/{id} → 200 with full booking details."""
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
    confirm = assert_200(
        client.post(
            f"/reservations/{res['reservation_id']}/confirm",
            json={"owner_token": res["owner_token"]},
        )
    )

    # Get booking
    booking = assert_200(client.get(f"/bookings/{confirm['booking_id']}"))

    assert booking["booking_id"] == confirm["booking_id"]
    assert booking["reservation_id"] == res["reservation_id"]
    assert booking["status"] == "confirmed"
    assert "seats" in booking
    assert len(booking["seats"]) == 2
    assert "total_cents" in booking
    assert "created_at" in booking

    # Verify seat details
    for s in booking["seats"]:
        assert "seat_id" in s
        assert "section" in s
        assert "row" in s
        assert "seat_label" in s
        assert "price_tier" in s


def test_get_booking_nonexistent(client):
    """GET /bookings/{nonexistent_id} → 404."""
    r = client.get(f"/bookings/{str(uuid.uuid4())}")
    assert_404(r)
