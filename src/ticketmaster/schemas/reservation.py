from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConfirmRequest(BaseModel):
    owner_token: uuid.UUID


class ReserveRequest(BaseModel):
    event_id: uuid.UUID
    seat_ids: list[uuid.UUID] = Field(min_length=1)
    user_id: uuid.UUID
    idempotency_key: str = Field(min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: uuid.UUID
    event_id: uuid.UUID
    seat_ids: list[uuid.UUID]
    user_id: uuid.UUID
    owner_token: uuid.UUID
    expires_at: datetime
    status: str

    model_config = {"from_attributes": True}
