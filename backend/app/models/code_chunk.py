import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, JSON, ForeignKey, ForeignKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UTCDateTime


class CodeChunk(Base, TimestampMixin):
    __tablename__ = "code_chunks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["file_id", "project_id"],
            ["project_files.id", "project_files.project_id"],
            ondelete="CASCADE",
        ),
        Index("ux_code_chunks_file_chunk_index", "file_id", "chunk_index", unique=True),
        Index("ix_code_chunks_symbol_name", "symbol_name"),
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="chunks", overlaps="chunks")

    file: Mapped["ProjectFile"] = relationship(
        "ProjectFile",
        back_populates="chunks",
        foreign_keys=[file_id],
        overlaps="chunks",
    )

    embeddings: Mapped[List["Embedding"]] = relationship(
        "Embedding",
        back_populates="chunk",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("code_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[List[float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ux_embeddings_chunk_model", "chunk_id", "model_name", unique=True),
    )

    # Relationships
    chunk: Mapped["CodeChunk"] = relationship("CodeChunk", back_populates="embeddings")
