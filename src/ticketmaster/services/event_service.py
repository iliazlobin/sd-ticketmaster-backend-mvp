from __future__ import annotations

import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ticketmaster.models.event import Event
from ticketmaster.models.seat import Seat
from ticketmaster.schemas.event import (
    EventListResponse,
    EventResponse,
    SearchResponse,
    SearchResult,
)
from ticketmaster.schemas.seat import SeatMapResponse, SeatResponse


class EventService:
    """Business logic for event browsing, search, and seat-map queries."""

    PAGE_SIZE = 20

    def __init__(self, db: AsyncSession, redis_client: redis.Redis | None = None) -> None:
        self.db = db
        self.redis = redis_client

    async def browse(
        self,
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
    ) -> EventListResponse:
        """Browse events with optional category, date range, and pagination."""
        # Build base query — exclude cancelled events
        base_query = select(Event).where(Event.status != "cancelled")

        if category:
            base_query = base_query.where(Event.category == category)
        if date_from:
            try:
                dt_from = datetime.fromisoformat(date_from)
                base_query = base_query.where(Event.event_date >= dt_from)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid date_from format",
                ) from None
        if date_to:
            try:
                dt_to = datetime.fromisoformat(date_to)
                base_query = base_query.where(Event.event_date <= dt_to)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid date_to format",
                ) from None

        # Count total (for pagination)
        count_query = select(func.count()).select_from(base_query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Paginate
        offset = (page - 1) * self.PAGE_SIZE
        query = base_query.offset(offset).limit(self.PAGE_SIZE).order_by(Event.event_date)
        result = await self.db.execute(query)
        events = result.scalars().all()

        # Build response with available seat counts
        event_responses = []
        for ev in events:
            seat_count = await self._count_available_seats(ev.event_id)
            event_responses.append(
                EventResponse(
                    event_id=ev.event_id,
                    name=ev.name,
                    performer=ev.performer,
                    venue=ev.venue,
                    category=ev.category,
                    event_date=ev.event_date,
                    status=ev.status,
                    available_seats=seat_count,
                )
            )

        return EventListResponse(
            events=event_responses,
            page=page,
            page_size=self.PAGE_SIZE,
            total=total,
        )

    async def search(self, query: str) -> SearchResponse:
        """Full-text search across event name, performer, and venue."""
        tsquery = func.plainto_tsquery(text("'english'"), query)
        tsvector = func.to_tsvector(
            text("'english'"),
            func.coalesce(Event.name, "")
            + text("' '")
            + func.coalesce(Event.performer, "")
            + text("' '")
            + func.coalesce(Event.venue, ""),
        )
        rank = func.ts_rank(tsvector, tsquery)

        stmt = (
            select(Event, rank.label("rank"))
            .where(tsvector.op("@@")(tsquery))
            .where(Event.status != "cancelled")
            .order_by(text("rank DESC"))
            .limit(50)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        results = [
            SearchResult(
                event_id=ev.event_id,
                name=ev.name,
                performer=ev.performer,
                venue=ev.venue,
                category=ev.category,
                event_date=ev.event_date,
                status=ev.status,
            )
            for ev, _rank in rows
        ]

        return SearchResponse(results=results)

    async def seat_map(self, event_id: uuid.UUID) -> SeatMapResponse:
        """View the seat map for an event with real-time availability status.

        Also releases any expired holds for seats in this event before returning results.
        """
        # Verify event exists
        ev = await self.db.get(Event, event_id)
        if ev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        # Release expired holds for this event
        await self._release_expired_holds(event_id)
        await self.db.commit()

        # Query seats
        stmt = (
            select(Seat)
            .where(Seat.event_id == event_id)
            .order_by(Seat.section, Seat.row, Seat.seat_label)
        )
        result = await self.db.execute(stmt)
        seats = result.scalars().all()

        seat_responses = [
            SeatResponse(
                seat_id=s.seat_id,
                section=s.section,
                row=s.row,
                seat_label=s.seat_label,
                price_tier=s.price_tier,
                status=s.status,
            )
            for s in seats
        ]

        return SeatMapResponse(event_id=event_id, seats=seat_responses)

    async def _count_available_seats(self, event_id: uuid.UUID) -> int:
        """Count seats with status='available' for an event."""
        stmt = select(func.count()).where(Seat.event_id == event_id, Seat.status == "available")
        result = await self.db.scalar(stmt)
        return result or 0

    async def _release_expired_holds(self, event_id: uuid.UUID) -> None:
        """Release seats held by expired reservations back to available."""
        from ticketmaster.models.reservation import Reservation

        now_utc = datetime.now(UTC)

        # Find expired pending reservations for this event
        expired_stmt = select(
            Reservation.reservation_id, Reservation.seat_ids, Reservation.owner_token
        ).where(
            Reservation.event_id == event_id,
            Reservation.status == "pending",
            Reservation.expires_at <= now_utc,
        )
        result = await self.db.execute(expired_stmt)
        expired_rows = result.all()

        for row in expired_rows:
            # Release seats: update status from held to available
            if row.seat_ids:
                stmt = text(
                    "UPDATE seats SET status='available', version=version+1 "
                    "WHERE seat_id = ANY(:seat_ids) AND status='held'"
                ).bindparams(seat_ids=row.seat_ids)
                await self.db.execute(stmt)

                # Release Redis locks for expired seats
                if self.redis is not None:
                    for seat_id in row.seat_ids:
                        lock_key = f"seat:{event_id}:{seat_id}"
                        current = await self.redis.get(lock_key)
                        if current is not None and current.decode() == str(row.owner_token):
                            await self.redis.delete(lock_key)

                # Mark reservation as expired
                await self.db.execute(
                    text(
                        "UPDATE reservations SET status='expired' "
                        "WHERE reservation_id = :rid AND status='pending'"
                    ).bindparams(rid=row.reservation_id),
                )
