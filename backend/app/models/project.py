import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, Integer, JSON, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UTCDateTime

# Where a project came from. Rows that existed before origins were tracked are 'unclassified'
# until a person reviews the evidence and classifies them; nothing is ever inferred from a name.
PROJECT_ORIGINS = ("unclassified", "user", "import", "upload", "git", "seed")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    languages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_indexed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unclassified")
    archived_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    # Relationships. Children are loaded only when asked for, and deletes rely on the database's
    # ON DELETE CASCADE (foreign keys are enforced on every connection, see database/connection.py).
    files: Mapped[List["ProjectFile"]] = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )
    chunks: Mapped[List["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )


class ProjectFile(Base, TimestampMixin):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language: Mapped[str] = mapped_column(String(64), default="plaintext", nullable=False)
    last_scanned_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="files")
    chunks: Mapped[List["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
        overlaps="chunks",
    )



# Project names are unique regardless of case (workspace folders collide case-insensitively on Windows).
Index("ux_projects_name_lower", func.lower(Project.name), unique=True)
Index("ux_project_files_project_path", ProjectFile.project_id, ProjectFile.file_path, unique=True)
Index("ux_project_files_id_project_id", ProjectFile.id, ProjectFile.project_id, unique=True)

