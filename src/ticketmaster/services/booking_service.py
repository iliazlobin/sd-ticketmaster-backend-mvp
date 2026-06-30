from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.models.booking import Booking, BookingSeat
from ticketmaster.models.seat import Seat
from ticketmaster.schemas.booking import BookingResponse, BookingSeatInfo


class BookingService:
    """Business logic for booking retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, booking_id: uuid.UUID) -> BookingResponse:
        """Retrieve booking details including seat assignments."""
        stmt = select(Booking).where(Booking.booking_id == booking_id)
        result = await self.db.execute(stmt)
        booking = result.scalar_one_or_none()

        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found",
            )

        # Query booking seats with seat details
        bs_stmt = (
            select(BookingSeat, Seat)
            .join(Seat, BookingSeat.seat_id == Seat.seat_id)
            .where(BookingSeat.booking_id == booking_id)
        )
        bs_result = await self.db.execute(bs_stmt)
        bs_rows = bs_result.all()

        seat_infos = [
            BookingSeatInfo(
                seat_id=seat.seat_id,
                section=seat.section,
                row=seat.row,
                seat_label=seat.seat_label,
                price_tier=seat.price_tier,
            )
            for _bs, seat in bs_rows
        ]

        return BookingResponse(
            booking_id=booking.booking_id,
            reservation_id=booking.reservation_id,
            user_id=booking.user_id,
            total_cents=booking.total_cents,
            status=booking.status,
            seats=seat_infos,
            created_at=booking.created_at,
        )
