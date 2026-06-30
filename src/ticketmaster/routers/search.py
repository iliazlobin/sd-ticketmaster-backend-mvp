from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.database import get_db
from ticketmaster.schemas.event import SearchResponse
from ticketmaster.services.event_service import EventService

search_router = APIRouter(prefix="/search", tags=["search"])


@search_router.get("", response_model=SearchResponse)
async def search_events(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Full-text search across event name, performer, and venue."""
    service = EventService(db)
    return await service.search(q)
