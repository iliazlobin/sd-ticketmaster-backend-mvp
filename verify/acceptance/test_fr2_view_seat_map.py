"""FR-2: View Seat Map

AC-2.1: GET /events/{event_id}/seats → 200 with seats array (section, row, seat_label, status, price_tier).
AC-2.2: Valid event with no seats → 200 with [].
AC-2.3: Non-existent event → 404.
"""

from verify.acceptance.conftest import assert_200, assert_404


def test_view_seat_map_success(client, test_event, test_seats):
    """GET /events/{event_id}/seats → 200 with seats having correct shape."""
    event_id = test_event["event_id"]
    r = client.get(f"/events/{event_id}/seats")
    body = assert_200(r)

    assert "event_id" in body
    assert body["event_id"] == event_id
    assert "seats" in body
    assert isinstance(body["seats"], list)

    if body["seats"]:
        seat = body["seats"][0]
        assert "seat_id" in seat, f"Seat missing 'seat_id': {seat}"
        assert "section" in seat, f"Seat missing 'section': {seat}"
        assert "row" in seat, f"Seat missing 'row': {seat}"
        assert "seat_label" in seat, f"Seat missing 'seat_label': {seat}"
        assert "status" in seat, f"Seat missing 'status': {seat}"
        assert seat["status"] in (
            "available",
            "held",
            "sold",
        ), f"Unexpected status: {seat['status']}"
        assert "price_tier" in seat


def test_view_seat_map_nonexistent_event(client):
    """GET /events/{nonexistent_id}/seats → 404."""
    r = client.get("/events/00000000-0000-0000-0000-000000000000/seats")
    assert_404(r)
