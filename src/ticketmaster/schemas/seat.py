from __future__ import annotations

import uuid

from pydantic import BaseModel


class SeatResponse(BaseModel):
    seat_id: uuid.UUID
    section: str
    row: str
    seat_label: str
    price_tier: str
    status: str

    model_config = {"from_attributes": True}


class SeatMapResponse(BaseModel):
    event_id: uuid.UUID
    seats: list[SeatResponse]
