from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ticketmaster.models.base import Base


class Seat(Base):
    __tablename__ = "seats"

    seat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.event_id"), nullable=False
    )
    section: Mapped[str] = mapped_column(Text, nullable=False)
    row: Mapped[str] = mapped_column(Text, nullable=False)
    seat_label: Mapped[str] = mapped_column(Text, nullable=False)
    price_tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="available")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("event_id", "seat_label", name="uq_seats_event_label"),
        CheckConstraint(
            "status IN ('available', 'held', 'sold')",
            name="ck_seats_status",
        ),
    )
