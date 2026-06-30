from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BookingSeatInfo(BaseModel):
    seat_id: uuid.UUID
    section: str
    row: str
    seat_label: str
    price_tier: str


class BookingResponse(BaseModel):
    booking_id: uuid.UUID
    reservation_id: uuid.UUID
    user_id: uuid.UUID
    total_cents: int
    status: str
    seats: list[BookingSeatInfo]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
