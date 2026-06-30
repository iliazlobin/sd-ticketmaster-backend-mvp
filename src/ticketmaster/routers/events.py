from __future__ import annotations

import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.database import get_db
from ticketmaster.redis import get_redis
from ticketmaster.schemas.event import EventListResponse
from ticketmaster.schemas.seat import SeatMapResponse
from ticketmaster.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventListResponse)
async def browse_events(
    category: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    radius: float | None = Query(None),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    """Browse events with optional category, date range, and location filters."""
    service = EventService(db)
    return await service.browse(
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )


@router.get("/{event_id}/seats", response_model=SeatMapResponse)
async def view_seat_map(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> SeatMapResponse:
    """View the seat map for an event with real-time availability."""
    service = EventService(db, redis_client=r)
    return await service.seat_map(event_id)
