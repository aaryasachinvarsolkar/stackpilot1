"""Code chunks and embeddings for AST parsing and semantic vector retrieval.

Additive only: adds `code_chunks` and `embeddings` tables, plus an integrity index
on `project_files (id, project_id)` to enforce consistent project/file ownership.
 * code_chunks: AST-derived code fragments linked to a project and project_file via composite FK.
 * embeddings: Vector representations per chunk and model (supports multiple models per chunk).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Unique index on project_files (id, project_id) to anchor the composite foreign key
    op.create_index(
        "ux_project_files_id_project_id",
        "project_files",
        ["id", "project_id"],
        unique=True,
    )

    # 2. code_chunks table
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(64), nullable=False),
        sa.Column("symbol_name", sa.String(255), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id", "project_id"],
            ["project_files.id", "project_files.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_code_chunks_file_chunk_index",
        "code_chunks",
        ["file_id", "chunk_index"],
        unique=True,
    )
    op.create_index("ix_code_chunks_project_id", "code_chunks", ["project_id"])
    op.create_index("ix_code_chunks_file_id", "code_chunks", ["file_id"])
    op.create_index("ix_code_chunks_symbol_name", "code_chunks", ["symbol_name"])

    # 3. embeddings table
    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_embeddings_chunk_model",
        "embeddings",
        ["chunk_id", "model_name"],
        unique=True,
    )
    op.create_index("ix_embeddings_chunk_id", "embeddings", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("embeddings")
    op.drop_table("code_chunks")
    op.drop_index("ux_project_files_id_project_id", table_name="project_files")
