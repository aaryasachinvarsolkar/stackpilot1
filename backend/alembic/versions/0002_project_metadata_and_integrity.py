"""Project origin/archival/scan metadata, file hashes and integrity indexes.

Additive only: no existing column or row value is modified.
 * projects.origin            NOT NULL, existing rows become 'unclassified' (never guessed)
 * projects.archived_at       NULL
 * projects.last_scanned_at   NULL
 * project_files.file_hash    NULL
 * unique index on lower(projects.name) and on (project_files.project_id, file_path)
 * lookup indexes on conversations.project_id and messages.conversation_id

A pre-flight check refuses to start if existing data would violate a new unique index, so a
failure happens before anything is changed. The migration also runs in a single transaction.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _preflight() -> None:
    bind = op.get_bind()
    dup_names = bind.execute(
        sa.text("SELECT lower(name) AS n, count(*) AS c FROM projects GROUP BY lower(name) HAVING count(*) > 1")
    ).fetchall()
    dup_files = bind.execute(
        sa.text(
            "SELECT project_id, file_path, count(*) AS c FROM project_files "
            "GROUP BY project_id, file_path HAVING count(*) > 1"
        )
    ).fetchall()
    problems = []
    if dup_names:
        problems.append("project names that differ only by case: " + ", ".join(sorted(r[0] for r in dup_names)))
    if dup_files:
        problems.append(f"{len(dup_files)} duplicated (project_id, file_path) pairs in project_files")
    if problems:
        raise RuntimeError(
            "Migration 0002 aborted before changing anything. Resolve first -> " + "; ".join(problems)
        )


def upgrade() -> None:
    _preflight()

    op.add_column("projects", sa.Column("origin", sa.String(16), nullable=False, server_default="unclassified"))
    op.add_column("projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_files", sa.Column("file_hash", sa.String(64), nullable=True))

    op.create_index("ux_projects_name_lower", "projects", [sa.text("lower(name)")], unique=True)
    op.create_index("ux_project_files_project_path", "project_files", ["project_id", "file_path"], unique=True)
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_index("ux_project_files_project_path", table_name="project_files")
    op.drop_index("ux_projects_name_lower", table_name="projects")

    # SQLite cannot drop columns in place on all versions; batch mode rebuilds the table only
    # when needed and preserves every remaining column's data.
    with op.batch_alter_table("project_files") as batch:
        batch.drop_column("file_hash")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("last_scanned_at")
        batch.drop_column("archived_at")
        batch.drop_column("origin")
