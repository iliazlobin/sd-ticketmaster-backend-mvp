"""create initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- events ---
    op.create_table(
        "events",
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("performer", sa.Text, nullable=False),
        sa.Column("venue", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_events_status",
        "events",
        "status IN ('scheduled', 'cancelled', 'completed')",
    )

    # --- seats ---
    op.create_table(
        "seats",
        sa.Column(
            "seat_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.event_id"), nullable=False),
        sa.Column("section", sa.Text, nullable=False),
        sa.Column("row", sa.Text, nullable=False),
        sa.Column("seat_label", sa.Text, nullable=False),
        sa.Column("price_tier", sa.Text, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'available'")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("event_id", "seat_label", name="uq_seats_event_label"),
    )
    op.create_check_constraint(
        "ck_seats_status",
        "seats",
        "status IN ('available', 'held', 'sold')",
    )
    op.create_index("idx_seats_event_status", "seats", ["event_id", "status"])

    # --- reservations ---
    op.create_table(
        "reservations",
        sa.Column(
            "reservation_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.event_id"), nullable=False),
        sa.Column("seat_ids", sa.ARRAY(UUID), nullable=False),
        sa.Column("owner_token", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_reservations_idempotency_key"),
    )
    op.create_check_constraint(
        "ck_reservations_status",
        "reservations",
        "status IN ('pending', 'confirmed', 'expired', 'cancelled')",
    )
    op.create_index("idx_reservations_user", "reservations", ["user_id"])

    # --- bookings ---
    op.create_table(
        "bookings",
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "reservation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("reservations.reservation_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("total_cents", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('confirmed', 'cancelled')",
    )

    # --- booking_seats ---
    op.create_table(
        "booking_seats",
        sa.Column(
            "booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.booking_id"), primary_key=True
        ),
        sa.Column("seat_id", UUID(as_uuid=True), nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table("booking_seats")
    op.drop_table("bookings")
    op.drop_table("reservations")
    op.drop_table("seats")
    op.drop_table("events")
