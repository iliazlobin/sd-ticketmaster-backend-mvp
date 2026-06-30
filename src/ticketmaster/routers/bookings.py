from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.database import get_db
from ticketmaster.schemas.booking import BookingResponse
from ticketmaster.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Retrieve booking details including seat assignments."""
    service = BookingService(db)
    return await service.get(booking_id)
