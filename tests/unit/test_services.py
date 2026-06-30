"""Isolated unit tests for ReservationService with mocked DB and Redis."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from ticketmaster.models.reservation import Reservation
from ticketmaster.models.seat import Seat
from ticketmaster.schemas.reservation import ConfirmRequest, ReserveRequest
from ticketmaster.services.reservation_service import ReservationService


class TestReserveSeats:
    """Unit tests for ReservationService.reserve()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_redis(self):
        r = AsyncMock()
        r.set = AsyncMock(return_value=True)
        return r

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        return ReservationService(mock_db, mock_redis)

    @pytest.fixture
    def event_id(self):
        return uuid.uuid4()

    @pytest.fixture
    def seat_ids(self, event_id):
        sid1 = uuid.uuid4()
        sid2 = uuid.uuid4()
        return [sid1, sid2]

    @pytest.fixture
    def seat_objects(self, event_id, seat_ids):
        return {
            seat_ids[0]: Seat(
                seat_id=seat_ids[0],
                event_id=event_id,
                section="A",
                row="1",
                seat_label="A1",
                price_tier="VIP",
                status="available",
            ),
            seat_ids[1]: Seat(
                seat_id=seat_ids[1],
                event_id=event_id,
                section="A",
                row="2",
                seat_label="A2",
                price_tier="Standard",
                status="available",
            ),
        }

    def _make_request(self, event_id, seat_ids):
        return ReserveRequest(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
        )

    async def test_reserve_success_returns_201(
        self, service, mock_db, mock_redis, event_id, seat_ids, seat_objects
    ):
        """Successful reservation returns ReserveResult with status_code=201."""
        # Mock: no existing idempotency check, then seat query,
        # then UPDATE seats, then UPDATE reservations
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        seats_mock = MagicMock()
        seats_mock.scalars.return_value.all.return_value = list(seat_objects.values())
        # Subsequent calls for raw SQL updates and reservation insert
        mock_db.execute = AsyncMock(
            side_effect=[
                no_existing,  # idempotency check
                seats_mock,  # seat query
                MagicMock(),  # UPDATE seats
                MagicMock(),  # refresh equivalent (commit triggers)
            ]
        )
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        result = await service.reserve(self._make_request(event_id, seat_ids))

        assert result.status_code == 201
        assert "reservation_id" in result.data
        assert result.data["status"] == "pending"
        assert len(result.data["seat_ids"]) == 2

    async def test_reserve_idempotent_retry_returns_200(
        self, service, mock_db, mock_redis, event_id, seat_ids
    ):
        """Duplicate idempotency key returns ReserveResult with status_code=200."""
        existing = Reservation(
            reservation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            event_id=event_id,
            seat_ids=list(seat_ids),
            owner_token=uuid.uuid4(),
            idempotency_key="dup-key",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            status="pending",
        )
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )

        req = ReserveRequest(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=uuid.uuid4(),
            idempotency_key="dup-key",
        )
        result = await service.reserve(req)

        assert result.status_code == 200
        assert result.data["status"] == "pending"

    async def test_reserve_different_payload_same_key_raises_422(
        self, service, mock_db, event_id, seat_ids
    ):
        """Different seat_ids with same idempotency_key raises 422."""
        existing = Reservation(
            reservation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            event_id=event_id,
            seat_ids=[seat_ids[0]],  # only one seat
            owner_token=uuid.uuid4(),
            idempotency_key="dup-key",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            status="pending",
        )
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )

        req = ReserveRequest(
            event_id=event_id,
            seat_ids=seat_ids,  # two seats — different
            user_id=uuid.uuid4(),
            idempotency_key="dup-key",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.reserve(req)
        assert exc_info.value.status_code == 422

    async def test_reserve_seat_wrong_event_raises_422(
        self, service, mock_db, mock_redis, event_id, seat_ids, seat_objects
    ):
        """Seat belonging to different event raises 422."""
        # No existing idempotency
        no_existing = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        seats_result = MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=list(seat_objects.values())))
            )
        )
        mock_db.execute = AsyncMock(side_effect=[no_existing, seats_result])

        wrong_event_id = uuid.uuid4()
        req = self._make_request(wrong_event_id, seat_ids)

        with pytest.raises(HTTPException) as exc_info:
            await service.reserve(req)
        assert exc_info.value.status_code == 422

    async def test_reserve_seat_already_held_raises_409(
        self, service, mock_db, mock_redis, event_id, seat_ids
    ):
        """Seat already held in Redis returns 409."""
        # No existing idempotency
        no_existing = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        # Return seat with status='held'
        held_seat = Seat(
            seat_id=seat_ids[0],
            event_id=event_id,
            section="A",
            row="1",
            seat_label="A1",
            price_tier="VIP",
            status="held",
        )
        seats_result = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[held_seat])))
        )
        mock_db.execute = AsyncMock(side_effect=[no_existing, seats_result])

        # Redis SET NX fails
        mock_redis.set = AsyncMock(return_value=False)

        req = ReserveRequest(
            event_id=event_id,
            seat_ids=[seat_ids[0]],
            user_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.reserve(req)
        assert exc_info.value.status_code == 409


class TestConfirmReservation:
    """Unit tests for ReservationService.confirm()."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.flush = AsyncMock()
        return db

    @pytest.fixture
    def mock_redis(self):
        r = AsyncMock()
        r.get = AsyncMock(return_value=None)
        return r

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        return ReservationService(mock_db, mock_redis)

    @pytest.fixture
    def reservation(self):
        rid = uuid.uuid4()
        eid = uuid.uuid4()
        return Reservation(
            reservation_id=rid,
            user_id=uuid.uuid4(),
            event_id=eid,
            seat_ids=[uuid.uuid4(), uuid.uuid4()],
            owner_token=uuid.uuid4(),
            idempotency_key="key1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            status="pending",
        )

    async def test_confirm_nonexistent_raises_404(self, service, mock_db):
        """Confirm non-existent reservation raises 404."""
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.confirm(uuid.uuid4(), ConfirmRequest(owner_token=uuid.uuid4()))
        assert exc_info.value.status_code == 404

    async def test_confirm_wrong_owner_token_raises_403(self, service, mock_db, reservation):
        """Confirm with wrong owner_token raises 403."""
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=reservation))
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.confirm(
                reservation.reservation_id,
                ConfirmRequest(owner_token=uuid.uuid4()),
            )
        assert exc_info.value.status_code == 403

    async def test_confirm_already_confirmed_raises_409(self, service, mock_db, reservation):
        """Confirm already-confirmed reservation raises 409."""
        reservation.status = "confirmed"
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=reservation))
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.confirm(
                reservation.reservation_id,
                ConfirmRequest(owner_token=reservation.owner_token),
            )
        assert exc_info.value.status_code == 409


class TestBookingService:
    """Unit tests for BookingService.get()."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    async def test_get_nonexistent_raises_404(self, mock_db):
        """Get non-existent booking raises 404."""
        from ticketmaster.services.booking_service import BookingService

        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        service = BookingService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid.uuid4())
        assert exc_info.value.status_code == 404
