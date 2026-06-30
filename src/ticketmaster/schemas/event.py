from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EventResponse(BaseModel):
    event_id: uuid.UUID
    name: str
    performer: str
    venue: str
    category: str
    event_date: datetime
    status: str
    available_seats: int = 0

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    events: list[EventResponse]
    page: int = Field(ge=1)
    page_size: int = 20
    total: int


class SearchResult(BaseModel):
    event_id: uuid.UUID
    name: str
    performer: str
    venue: str
    category: str
    event_date: datetime
    status: str

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    results: list[SearchResult]
