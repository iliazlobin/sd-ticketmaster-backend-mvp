from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.config import settings
from ticketmaster.models.booking import Booking, BookingSeat
from ticketmaster.models.reservation import Reservation
from ticketmaster.models.seat import Seat
from ticketmaster.schemas.reservation import ConfirmRequest, ReserveRequest

# Lua script to release locks: only delete keys whose value matches owner_token
RELEASE_LOCKS_SCRIPT = """
local released = 0
for _, key in ipairs(KEYS) do
    local current = redis.call('GET', key)
    if current == ARGV[1] then
        redis.call('DEL', key)
        released = released + 1
    end
end
return released
"""


@dataclass
class ReserveResult:
    status_code: int
    data: dict


class ReservationService:
    """Business logic for seat reservation, confirmation, and expiry cleanup."""

    def __init__(self, db: AsyncSession, redis_client: redis.Redis) -> None:
        self.db = db
        self.redis = redis_client

    async def reserve(self, body: ReserveRequest) -> ReserveResult:
        """Atomically reserve seats with Redis SETNX. All-or-nothing.

        Returns 201 on new reservation, 200 on idempotent retry.
        Raises HTTPException for conflicts (409) or validation errors (422).
        """
        # --- Idempotency check ---
        existing = await self._find_by_idempotency_key(body.idempotency_key)
        if existing:
            # Same key exists — validate payload matches
            if set(existing.seat_ids) != set(body.seat_ids):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Idempotency key reused with different seat_ids",
                )
            if existing.event_id != body.event_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Idempotency key reused with different event_id",
                )
            # Return existing reservation (200)
            return ReserveResult(
                status_code=200,
                data={
                    "reservation_id": str(existing.reservation_id),
                    "event_id": str(existing.event_id),
                    "seat_ids": [str(s) for s in existing.seat_ids],
                    "user_id": str(existing.user_id),
                    "owner_token": str(existing.owner_token),
                    "expires_at": existing.expires_at.isoformat(),
                    "status": existing.status,
                },
            )

        # --- Validate seats exist and belong to the event ---
        seat_ids = body.seat_ids
        stmt = select(Seat).where(Seat.seat_id.in_(seat_ids))
        result = await self.db.execute(stmt)
        seats = {s.seat_id: s for s in result.scalars().all()}

        if len(seats) != len(seat_ids):
            missing = set(seat_ids) - set(seats.keys())
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Seats not found: {missing}",
            )

        for seat in seats.values():
            if seat.event_id != body.event_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Seat {seat.seat_id} does not belong to event {body.event_id}",
                )

        # --- Redis lock acquisition ---
        owner_token = uuid.uuid4()
        ttl_seconds = settings.seat_hold_ttl
        locked_keys: list[str] = []

        for seat_id in seat_ids:
            key = f"seat:{body.event_id}:{seat_id}"
            # SET key value NX EX ttl
            acquired = await self.redis.set(key, str(owner_token), nx=True, ex=ttl_seconds)
            if acquired:
                locked_keys.append(key)
            else:
                # Seat lock exists in Redis — check if actually available in DB
                # (stale lock from expired reservation)
                seat = seats.get(seat_id)
                if seat is not None and seat.status == "available":
                    # Stale lock — attempt to clean it up and retry
                    current_val = await self.redis.get(key)
                    if current_val is not None:
                        # Check if the owning reservation has expired
                        owner_str = current_val.decode()
                        try:
                            owner_uuid = uuid.UUID(owner_str)
                            stmt_check = select(Reservation).where(
                                Reservation.owner_token == owner_uuid,
                                Reservation.status == "pending",
                            )
                            check_result = await self.db.execute(stmt_check)
                            owning_res = check_result.scalar_one_or_none()
                            if owning_res is None or owning_res.expires_at <= datetime.now(UTC):
                                # Expired — release stale lock
                                await self.redis.delete(key)
                                # Retry the lock acquisition
                                acquired = await self.redis.set(
                                    key, str(owner_token), nx=True, ex=ttl_seconds
                                )
                                if acquired:
                                    locked_keys.append(key)
                                    continue
                        except (ValueError, KeyError):
                            pass
                # Could not recover — release all acquired locks and fail
                await self._release_locks(locked_keys, str(owner_token))
                conflicting = await self._find_conflicting(seat_ids, seats)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "detail": "One or more seats are unavailable",
                        "conflicting_seat_ids": conflicting,
                    },
                )

        # --- All locks acquired — persist reservation ---
        now_utc = datetime.now(UTC)
        expires_at = now_utc + timedelta(seconds=ttl_seconds)

        reservation = Reservation(
            reservation_id=uuid.uuid4(),
            user_id=body.user_id,
            event_id=body.event_id,
            seat_ids=list(seat_ids),
            owner_token=owner_token,
            idempotency_key=body.idempotency_key,
            expires_at=expires_at,
            status="pending",
        )
        self.db.add(reservation)

        # Update seats to 'held'
        await self.db.execute(
            text(
                "UPDATE seats SET status='held', version=version+1 "
                "WHERE seat_id = ANY(:seat_ids) AND status='available'"
            ).bindparams(seat_ids=list(seat_ids)),
        )

        await self.db.commit()
        await self.db.refresh(reservation)

        return ReserveResult(
            status_code=201,
            data={
                "reservation_id": str(reservation.reservation_id),
                "event_id": str(reservation.event_id),
                "seat_ids": [str(s) for s in reservation.seat_ids],
                "user_id": str(reservation.user_id),
                "owner_token": str(reservation.owner_token),
                "expires_at": reservation.expires_at.isoformat(),
                "status": reservation.status,
            },
        )

    async def confirm(self, reservation_id: uuid.UUID, body: ConfirmRequest) -> dict:
        """Confirm a held reservation with OCC fencing and simulated payment.

        Returns booking details on success.
        Raises 404 (not found), 403 (wrong token), 410 (expired), 409 (already confirmed).
        """
        # Look up reservation
        stmt = select(Reservation).where(Reservation.reservation_id == reservation_id)
        result = await self.db.execute(stmt)
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        # --- Fencing: verify owner_token ---
        if reservation.owner_token != body.owner_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid owner_token",
            )

        # --- Already confirmed? ---
        if reservation.status == "confirmed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation already confirmed",
            )

        # --- Expiry check ---
        now_utc = datetime.now(UTC)
        if reservation.expires_at <= now_utc:
            # Release seats and mark expired
            await self._expire_reservation(reservation)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Reservation expired",
            )

        # Also check Redis lock expiry
        for seat_id in reservation.seat_ids:
            key = f"seat:{reservation.event_id}:{seat_id}"
            lock_val = await self.redis.get(key)
            if lock_val is None or lock_val.decode() != str(reservation.owner_token):
                await self._expire_reservation(reservation)
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Reservation expired",
                )

        # --- OCC: update seats from held to sold ---
        seat_ids_list = list(reservation.seat_ids)

        # First, verify all seats are still held
        seat_stmt = select(Seat).where(Seat.seat_id.in_(seat_ids_list))
        seat_result = await self.db.execute(seat_stmt)
        seat_objs = {s.seat_id: s for s in seat_result.scalars().all()}

        for seat_id in seat_ids_list:
            seat = seat_objs.get(seat_id)
            if seat is None or seat.status != "held":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Seats are no longer held",
                )

        # OCC update: only update if status is still 'held'
        await self.db.execute(
            text(
                "UPDATE seats SET status='sold', version=version+1 "
                "WHERE seat_id = ANY(:seat_ids) AND status='held'"
            ).bindparams(seat_ids=seat_ids_list),
        )

        # --- Create booking ---
        booking = Booking(
            booking_id=uuid.uuid4(),
            reservation_id=reservation.reservation_id,
            user_id=reservation.user_id,
            total_cents=0,
            status="confirmed",
        )
        self.db.add(booking)
        await self.db.flush()

        # Insert booking_seats
        for seat_id in seat_ids_list:
            bs = BookingSeat(booking_id=booking.booking_id, seat_id=seat_id)
            self.db.add(bs)

        # Mark reservation as confirmed
        reservation.status = "confirmed"

        # Release Redis locks
        lock_keys = [f"seat:{reservation.event_id}:{sid}" for sid in seat_ids_list]
        await self._release_locks(lock_keys, str(reservation.owner_token))

        await self.db.commit()
        await self.db.refresh(booking)

        # Build response with seat details
        seat_details = [
            {
                "seat_id": str(seat_objs[sid].seat_id),
                "section": seat_objs[sid].section,
                "row": seat_objs[sid].row,
                "seat_label": seat_objs[sid].seat_label,
                "price_tier": seat_objs[sid].price_tier,
            }
            for sid in seat_ids_list
        ]

        return {
            "booking_id": str(booking.booking_id),
            "reservation_id": str(reservation.reservation_id),
            "user_id": str(booking.user_id),
            "total_cents": booking.total_cents,
            "status": booking.status,
            "seats": seat_details,
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
        }

    async def _find_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        """Find an existing reservation by idempotency key."""
        stmt = select(Reservation).where(Reservation.idempotency_key == idempotency_key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _release_locks(self, keys: list[str], owner_token: str) -> None:
        """Release Redis locks that match the given owner_token."""
        if not keys:
            return
        script = self.redis.register_script(RELEASE_LOCKS_SCRIPT)
        await script(keys=keys, args=[owner_token])

    async def _find_conflicting(
        self, seat_ids: list[uuid.UUID], seats: dict[uuid.UUID, Seat]
    ) -> list[str]:
        """Find which seat_ids are unavailable (not in 'available' state)."""
        conflicting = []
        for sid in seat_ids:
            seat = seats.get(sid)
            if seat is None or seat.status != "available":
                conflicting.append(str(sid))
        # Also check DB for any seats that were already held/sold
        if not conflicting:
            stmt = select(Seat.seat_id).where(
                Seat.seat_id.in_(seat_ids), Seat.status != "available"
            )
            result = await self.db.execute(stmt)
            conflicting = [str(row[0]) for row in result.all()]
        return conflicting

    async def _expire_reservation(self, reservation: Reservation) -> None:
        """Release seats and mark reservation as expired."""
        seat_ids_list = list(reservation.seat_ids)

        # Release seats back to available
        await self.db.execute(
            text(
                "UPDATE seats SET status='available', version=version+1 "
                "WHERE seat_id = ANY(:seat_ids) AND status='held'"
            ).bindparams(seat_ids=seat_ids_list),
        )

        # Mark reservation expired
        reservation.status = "expired"

        # Release Redis locks
        lock_keys = [f"seat:{reservation.event_id}:{sid}" for sid in seat_ids_list]
        await self._release_locks(lock_keys, str(reservation.owner_token))

        await self.db.commit()
