from __future__ import annotations

import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.database import get_db
from ticketmaster.redis import get_redis
from ticketmaster.schemas.reservation import ConfirmRequest, ReserveRequest
from ticketmaster.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("")
async def reserve_seats(
    body: ReserveRequest,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """Reserve seats atomically with a 10-minute hold.

    Returns 201 on new reservation, 200 on idempotent retry.
    """
    service = ReservationService(db, r)
    result = await service.reserve(body)
    # Determine status code: 200 for idempotent retry, 201 for new
    if result.status_code == 200:
        return JSONResponse(content=result.data, status_code=200)
    return JSONResponse(content=result.data, status_code=201)


@router.post("/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: uuid.UUID,
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """Confirm a held reservation and simulate payment."""
    service = ReservationService(db, r)
    return await service.confirm(reservation_id, body)
