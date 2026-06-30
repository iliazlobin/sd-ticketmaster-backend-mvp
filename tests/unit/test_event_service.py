"""Isolated unit tests for EventService with mocked DB."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ticketmaster.models.event import Event
from ticketmaster.models.seat import Seat
from ticketmaster.services.event_service import EventService


class TestEventServiceBrowse:
    """Unit tests for EventService.browse()."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return EventService(mock_db)

    @pytest.fixture
    def sample_event(self):
        return Event(
            event_id=uuid.uuid4(),
            name="Test Event",
            performer="Test Performer",
            venue="Test Venue",
            category="music",
            event_date=datetime(2026, 7, 4, tzinfo=UTC),
            status="scheduled",
        )

    async def test_browse_no_filters_returns_event_list(self, service, mock_db, sample_event):
        """Browse with no filters returns paginated events with available seat counts."""
        # Mock: count query returns 1
        mock_db.scalar = AsyncMock(return_value=1)
        # Mock: event query returns [sample_event]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_event]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.browse(page=1)

        assert result.page == 1
        assert result.page_size == 20
        assert result.total == 1
        assert len(result.events) == 1
        assert result.events[0].name == "Test Event"

    async def test_browse_with_category_filter(self, service, mock_db, sample_event):
        """Browse with category filter passes category to query."""
        mock_db.scalar = AsyncMock(return_value=1)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_event]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.browse(category="music", page=1)

        assert result.total == 1
        assert len(result.events) == 1

    async def test_browse_empty_page(self, service, mock_db):
        """Browse with high page number returns empty events list."""
        mock_db.scalar = AsyncMock(return_value=3)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.browse(page=999)

        assert result.events == []
        assert result.total == 3
        assert result.page == 999

    async def test_browse_invalid_date_format_raises_422(self, service, mock_db):
        """Browse with invalid date_from raises 422."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.browse(date_from="not-a-date", page=1)
        assert exc_info.value.status_code == 422

    async def test_browse_available_seats_count(self, service, mock_db, sample_event):
        """Browse computes available_seats per event via subquery."""
        mock_db.scalar = AsyncMock(side_effect=[1, 5])  # total=1, seat_count=5
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_event]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.browse(page=1)

        assert result.events[0].available_seats == 5


class TestEventServiceSeatMap:
    """Unit tests for EventService.seat_map()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return EventService(mock_db)

    async def test_seat_map_nonexistent_event_returns_404(self, service, mock_db):
        """Seat map for non-existent event raises 404."""
        mock_db.get = AsyncMock(return_value=None)
        from fastapi import HTTPException

        fake_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await service.seat_map(fake_id)
        assert exc_info.value.status_code == 404

    async def test_seat_map_returns_seats_ordered(self, service, mock_db):
        """Seat map returns seats sorted by section, row, seat_label."""
        event_id = uuid.uuid4()
        ev = Event(
            event_id=event_id,
            name="Test",
            performer="P",
            venue="V",
            category="music",
            event_date=datetime(2026, 7, 4, tzinfo=UTC),
            status="scheduled",
        )
        mock_db.get = AsyncMock(return_value=ev)

        # Mock expired holds query returns empty
        mock_expired_result = MagicMock()
        mock_expired_result.all.return_value = []
        # Mock seats query
        seat = Seat(
            seat_id=uuid.uuid4(),
            event_id=event_id,
            section="A",
            row="1",
            seat_label="A1",
            price_tier="VIP",
            status="available",
        )
        mock_seat_result = MagicMock()
        mock_seat_result.scalars.return_value.all.return_value = [seat]

        mock_db.execute = AsyncMock(side_effect=[mock_expired_result, mock_seat_result])

        result = await service.seat_map(event_id)

        assert result.event_id == event_id
        assert len(result.seats) == 1
        assert result.seats[0].seat_label == "A1"
        assert result.seats[0].status == "available"


class TestEventServiceSearch:
    """Unit tests for EventService.search()."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return EventService(mock_db)

    async def test_search_returns_ranked_results(self, service, mock_db):
        """Search returns results with rank ordering."""
        event_id = uuid.uuid4()
        ev = Event(
            event_id=event_id,
            name="Taylor Swift",
            performer="Taylor Swift",
            venue="Stadium",
            category="music",
            event_date=datetime(2026, 7, 4, tzinfo=UTC),
            status="scheduled",
        )
        mock_result = MagicMock()
        mock_result.all.return_value = [(ev, 0.5)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.search("taylor")

        assert len(result.results) == 1
        assert result.results[0].name == "Taylor Swift"

    async def test_search_no_results(self, service, mock_db):
        """Search with no matches returns empty results."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.search("xyzzy123")

        assert result.results == []


class TestEventServiceExpiredHolds:
    """Unit tests for _release_expired_holds()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return EventService(mock_db)

    async def test_release_expired_holds_no_expired(self, service, mock_db):
        """No expired holds → no updates."""
        event_id = uuid.uuid4()
        ev = Event(
            event_id=event_id,
            name="T",
            performer="P",
            venue="V",
            category="music",
            event_date=datetime(2026, 7, 4, tzinfo=UTC),
            status="scheduled",
        )
        mock_db.get = AsyncMock(return_value=ev)

        mock_expired_result = MagicMock()
        mock_expired_result.all.return_value = []
        mock_seat_result = MagicMock()
        mock_seat_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[mock_expired_result, mock_seat_result])

        result = await service.seat_map(event_id)
        assert result.event_id == event_id
