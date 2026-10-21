"""Grounded answers: status and citation metadata on messages.

Additive only: no existing column or row value is modified.
 * messages.status     VARCHAR(24) NULL   answered_verified | answered_unverified | not_in_context | unavailable
 * messages.grounding  JSON NULL          retrieval counts and citation metadata (ranges, statuses, hashes); never source text

Every existing message keeps NULL in both columns. NULL means "legacy": the message was written before answers were grounded,
so it is never presented as verified. Nothing is back-filled or guessed.

The downgrade removes exactly these two columns and nothing else.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("status", sa.String(24), nullable=True))
    op.add_column("messages", sa.Column("grounding", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Batch mode: SQLite versions without ALTER TABLE ... DROP COLUMN rebuild the table, keeping every other column's data.
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("grounding")
        batch.drop_column("status")
