"""FR-1: Browse Events

AC-1.1: GET /events?category=music&date_from=...&date_to=...&lat=...&lon=...&radius=...&page=1 → 200 with paginated results.
AC-1.2: Empty page → 200 with [].
AC-1.3: Missing required params → 422 (page must be numeric; query params with invalid values should 422).
"""

from verify.acceptance.conftest import assert_200, assert_422


def test_browse_events_with_filters(client):
    """GET /events with valid filters → 200 with paginated results and correct shape."""
    params = {
        "category": "music",
        "date_from": "2026-01-01",
        "date_to": "2026-12-31",
        "page": 1,
    }
    r = client.get("/events", params=params)
    body = assert_200(r)

    assert "events" in body, f"Response missing 'events' key: {body}"
    events = body["events"]
    assert isinstance(events, list), f"'events' is not a list: {type(events)}"
    assert "page" in body
    assert body["page"] == 1
    assert "page_size" in body
    assert "total" in body
    assert body["total"] >= len(events)

    # Verify event shape
    if events:
        ev = events[0]
        assert "event_id" in ev
        assert "name" in ev
        assert "performer" in ev
        assert "venue" in ev
        assert "category" in ev
        assert "event_date" in ev
        assert "status" in ev
        assert "available_seats" in ev


def test_browse_events_empty_page(client):
    """GET /events with a very high page number → 200 with empty events list."""
    r = client.get("/events", params={"page": 99999})
    body = assert_200(r)
    assert body["events"] == [], f"Expected empty events list, got: {body['events']}"
    assert body["total"] >= 0


def test_browse_events_invalid_page(client):
    """GET /events with non-numeric page → 422."""
    assert_422(client.get("/events", params={"page": "abc"}))
