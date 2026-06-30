"""FR-8: Idempotent Reservation

AC-8.1: Same idempotency_key submitted twice → 200 with original reservation (not 201, not 409).
AC-8.2: Different seat_ids with same idempotency_key → 422.
"""

import uuid

from verify.acceptance.conftest import (
    assert_200,
    assert_201,
)


def test_idempotent_reservation_same_payload(client, test_event, available_seats):
    """POST /reservations with same idempotency_key twice → 200 with same reservation."""
    seats = available_seats[:2]
    assert len(seats) >= 2, "Need at least 2 available seats for this test"

    payload = {
        "event_id": test_event["event_id"],
        "seat_ids": [s["seat_id"] for s in seats],
        "user_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
    }

    # First call — creates reservation
    res1 = assert_201(client.post("/reservations", json=payload))

    # Second call with same idempotency_key — returns existing reservation
    r2 = client.post("/reservations", json=payload)
    res2 = assert_200(r2)

    assert (
        res2["reservation_id"] == res1["reservation_id"]
    ), f"Idempotent retry returned different reservation: {res2['reservation_id']} != {res1['reservation_id']}"
    assert res2["seat_ids"] == res1["seat_ids"]
    assert res2["owner_token"] == res1["owner_token"]
    assert res2["status"] == "pending"


def test_idempotent_reservation_different_payload(client, test_event, available_seats):
    """Same idempotency_key with different seat_ids → 422."""
    seats = available_seats[:3]
    assert len(seats) >= 3, "Need at least 3 available seats for this test"

    idem_key = str(uuid.uuid4())

    # First reservation with seats[0]
    res1 = assert_201(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[0]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": idem_key,
            },
        )
    )

    # Same idempotency_key, different seats → 422
    r2 = client.post(
        "/reservations",
        json={
            "event_id": test_event["event_id"],
            "seat_ids": [seats[1]["seat_id"]],  # different seat
            "user_id": str(uuid.uuid4()),
            "idempotency_key": idem_key,  # same key
        },
    )
    assert r2.status_code == 422, (
        f"Expected 422 for same idempotency_key with different payload, "
        f"got {r2.status_code}: {r2.text}"
    )


def test_idempotent_reservation_idempotency_key_format(client, test_event, available_seats):
    """Any non-empty idempotency_key string is accepted."""
    seats = available_seats[:1]
    assert len(seats) >= 1, "Need at least 1 available seat"

    key = "my-custom-key-123"
    res = assert_201(
        client.post(
            "/reservations",
            json={
                "event_id": test_event["event_id"],
                "seat_ids": [seats[0]["seat_id"]],
                "user_id": str(uuid.uuid4()),
                "idempotency_key": key,
            },
        )
    )

    assert res["status"] == "pending"
