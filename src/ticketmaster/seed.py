"""Idempotent demo-data seeder.

The acceptance suite (verify/acceptance) is black-box and discovers test data via
``GET /events`` — it requires at least one event with several available seats, but the
public API has no event-creation endpoint, so events can only be inserted at the DB
layer. This module provides the seed the design calls for.

Guarded by the ``SEED_DEMO_DATA`` environment variable (off by default) so it never
runs in production; compose/e2e set it to ``1``. Idempotent: it does nothing if any
event already exists.

Run as a module after migrations:  ``python -m ticketmaster.seed``
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ticketmaster.config import settings
from ticketmaster.models.event import Event
from ticketmaster.models.seat import Seat

# 3 sections x 5 rows x 4 seats = 60 available seats — ample headroom for the
# acceptance suite, which reserves/sells a few dozen across its run.
_SECTIONS = (("A", "VIP"), ("B", "Premium"), ("C", "GA"))
_ROWS = range(1, 6)
_SEATS_PER_ROW = range(1, 5)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


async def seed() -> int:
    """Insert one demo event with 60 available seats if the DB has no events.

    Returns the number of seats inserted (0 if seeding was skipped).
    """
    engine = create_async_engine(settings.database_url, echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            existing = (
                await session.execute(select(func.count()).select_from(Event))
            ).scalar_one()
            if existing:
                print(f"[seed] {existing} event(s) already present — skipping demo seed")
                return 0

            event = Event(
                name="Taylor Swift | The Eras Tour",
                performer="Taylor Swift",
                venue="MetLife Stadium",
                category="music",
                event_date=datetime.now(UTC) + timedelta(days=30),
                status="scheduled",
            )
            session.add(event)
            await session.flush()  # populate event.event_id

            count = 0
            for section, tier in _SECTIONS:
                for row in _ROWS:
                    for seat_no in _SEATS_PER_ROW:
                        session.add(
                            Seat(
                                event_id=event.event_id,
                                section=section,
                                row=str(row),
                                seat_label=f"{section}{row}-{seat_no}",
                                price_tier=tier,
                                status="available",
                                version=0,
                            )
                        )
                        count += 1

            await session.commit()
            print(f"[seed] inserted 1 event ({event.event_id}) with {count} available seats")
            return count
    finally:
        await engine.dispose()


def main() -> None:
    if not _truthy(os.environ.get("SEED_DEMO_DATA")):
        print("[seed] SEED_DEMO_DATA not set — skipping (no demo data in production)")
        return
    asyncio.run(seed())


if __name__ == "__main__":
    main()
