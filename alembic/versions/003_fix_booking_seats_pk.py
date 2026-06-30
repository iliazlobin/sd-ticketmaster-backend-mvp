"""fix booking_seats primary key to composite (booking_id, seat_id)

Revision ID: 003
Revises: 002
Create Date: 2026-06-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop existing PK constraint and recreate as composite
    op.execute("ALTER TABLE booking_seats DROP CONSTRAINT IF EXISTS booking_seats_pkey")
    op.execute("ALTER TABLE booking_seats ADD PRIMARY KEY (booking_id, seat_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE booking_seats DROP CONSTRAINT IF EXISTS booking_seats_pkey")
    op.execute("ALTER TABLE booking_seats ADD PRIMARY KEY (booking_id)")
