from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project


async def get_project_or_404(project_id: str, db: AsyncSession = Depends(get_db)) -> Project:
    """Look a project up by id, then by name. Unknown projects are a 404, never a fallback."""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().first()
    if project is None:
        project = (await db.execute(select(Project).where(Project.name == project_id))).scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return project
