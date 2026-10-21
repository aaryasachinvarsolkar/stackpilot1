from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_or_404
from app.database import get_db
from app.models.project import Project
from app.services.indexer import (
    IndexingJobStatus,
    get_current_job_status,
    get_project_lock,
    index_project_workspace,
)

router = APIRouter(prefix="/api/projects/{project_id}/index", tags=["indexing"])


class IndexJobResponse(BaseModel):
    project_id: str
    status: str
    files_scanned: int
    files_indexed: int
    files_unchanged: int
    files_removed: int
    chunks_created: int
    errors: List[str]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None

    @classmethod
    def from_job_status(cls, job: IndexingJobStatus) -> "IndexJobResponse":
        return cls(
            project_id=job.project_id,
            status=job.status,
            files_scanned=job.files_scanned,
            files_indexed=job.files_indexed,
            files_unchanged=job.files_unchanged,
            files_removed=job.files_removed,
            chunks_created=job.chunks_created,
            errors=job.errors,
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=job.duration_seconds,
        )


@router.post("", response_model=IndexJobResponse, summary="Trigger Project Codebase Indexing")
async def trigger_project_indexing(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Index supported source files with AST symbol parsing.

    Returns 409 if an indexing job is already in progress for this project.
    """
    lock = await get_project_lock(project.id)
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An indexing job is already in progress for this project.",
        )

    try:
        job = await index_project_workspace(project, db)
    except RuntimeError as r_exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(r_exc),
        )

    return IndexJobResponse.from_job_status(job)


@router.get("/status", response_model=IndexJobResponse, summary="Get Indexing Job Status")
async def get_project_indexing_status(
    project: Project = Depends(get_project_or_404),
):
    """Return the status and metrics of the current or most recent indexing job."""
    job = get_current_job_status(project.id)
    return IndexJobResponse.from_job_status(job)
