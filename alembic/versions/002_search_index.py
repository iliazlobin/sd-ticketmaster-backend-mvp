"""add full-text search index for events

Revision ID: 002
Revises: 001
Create Date: 2026-06-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX idx_events_search ON events
        USING GIN (
            to_tsvector('english',
                coalesce(name, '') || ' '
                || coalesce(performer, '') || ' '
                || coalesce(venue, ''))
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_events_search", table_name="events")
