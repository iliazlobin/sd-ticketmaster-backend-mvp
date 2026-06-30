"""FR-3: Search Events

AC-3.1: GET /search?q=swift → 200 with ranked results.
AC-3.2: GET /search?q=xyzzy123 → 200 with [].
AC-3.3: Empty query → 422.
"""

from verify.acceptance.conftest import assert_200, assert_422


def test_search_returns_results(client, test_event):
    """GET /search?q=<existing keyword> → 200 with results containing the matched event."""
    # Use part of the event name or performer as search query
    query = test_event["name"].split()[0]
    r = client.get("/search", params={"q": query})
    body = assert_200(r)

    assert "results" in body, f"Response missing 'results' key: {body}"
    assert isinstance(body["results"], list)

    # The test event should appear in results
    found_ids = [ev["event_id"] for ev in body["results"]]
    assert (
        test_event["event_id"] in found_ids
    ), f"Test event {test_event['event_id']} not found in search results for '{query}': {found_ids}"

    # Verify result shape
    if body["results"]:
        ev = body["results"][0]
        assert "event_id" in ev
        assert "name" in ev
        assert "performer" in ev
        assert "venue" in ev
        assert "category" in ev
        assert "event_date" in ev
        assert "status" in ev


def test_search_no_results(client):
    """GET /search?q=<nonsense> → 200 with empty results."""
    r = client.get("/search", params={"q": "xyzzy123_nonexistent_event_query"})
    body = assert_200(r)
    assert body["results"] == [], f"Expected empty results, got: {body['results']}"


def test_search_empty_query(client):
    """GET /search with empty q → 422."""
    r = client.get("/search", params={"q": ""})
    assert_422(r)


def test_search_missing_query(client):
    """GET /search with no q param → 422."""
    r = client.get("/search")
    assert_422(r)
