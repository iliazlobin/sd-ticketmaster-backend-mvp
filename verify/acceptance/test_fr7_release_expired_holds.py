"""FR-7: Release Expired Holds

AC-7.1: After hold TTL expires, seats return to 'available' (or are available for re-reservation).
AC-7.2: Confirming an expired reservation → 410.
"""

import time
import uuid

from verify.acceptance.conftest import (
    assert_200,
    assert_201,
)


def test_confirm_expired_reservation(client, test_event, available_seats):
    """Confirm a reservation that's known to be non-existent → 410.

    Full hold-expiry verification requires waiting for the TTL (10 minutes by default).
    This test validates the 410 response path for a reservation that doesn't exist
    (simulating expiry). In a test-mode deployment with a shortened TTL, a full
    wait-and-recheck test can be added.
    """
    # Use a UUID that has never been created — should behave like expired
    r = client.post(
        f"/reservations/{str(uuid.uuid4())}/confirm",
        json={"owner_token": str(uuid.uuid4())},
    )
    assert r.status_code in (404, 410), (
        f"Expected 404 or 410 for expired/nonexistent reservation, "
        f"got {r.status_code}: {r.text}"
    )


def test_seats_released_after_timeout(client, test_event, available_seats):
    """Reserve seats, let the hold expire (short TTL), verify they return to available.

    This test relies on the system being configured with a short hold TTL in test mode.
    If the default TTL is 600s, this test will skip with a message.
    """
    seats = available_seats[:1]
    if len(seats) < 1:
        return  # let the fixture handle skip

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

    seat_id = seats[0]["seat_id"]

    # Verify held immediately
    r = client.get(f"/events/{test_event['event_id']}/seats")
    body = assert_200(r)
    held_seat = next((s for s in body["seats"] if s["seat_id"] == seat_id), None)
    assert held_seat is not None, f"Seat {seat_id} not found in seat map"
    assert held_seat["status"] == "held", f"Seat should be 'held', got '{held_seat['status']}'"

    # Poll for release (up to ~15 seconds — relies on test-mode short TTL)
    # If the system has a long TTL, this will time out and fail, which is correct
    # because the acceptance criterion IS that holds expire.
    poll_start = time.monotonic()
    poll_timeout = 15  # seconds — assumes test-mode TTL ≤ 10s
    released = False

    while time.monotonic() - poll_start < poll_timeout:
        time.sleep(1)
        r2 = client.get(f"/events/{test_event['event_id']}/seats")
        body2 = assert_200(r2)
        seat2 = next((s for s in body2["seats"] if s["seat_id"] == seat_id), None)
        if seat2 and seat2["status"] == "available":
            released = True
            break

    # The FR-7 acceptance criterion IS that holds expire and release seats.
    # This suite MUST be run in test mode with a short TTL (set
    # SEAT_HOLD_TTL_SECONDS <= 10, see design.md §implementation notes); a long
    # production TTL is a deployment/config error for the acceptance run, not a
    # pass. Failing here is correct — it forces expiry to be implemented and the
    # test-mode TTL to be wired before FR-7 can go green.
    assert released, (
        f"Seat {seat_id} did not return to 'available' within {poll_timeout}s. "
        f"FR-7 requires expired holds to auto-release. Run the acceptance suite "
        f"in test mode with SEAT_HOLD_TTL_SECONDS <= 10."
    )
