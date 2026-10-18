import logging
import os
import shutil
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_or_404
from app.database import get_db
from app.models.project import Project
from app.services.workspace import (
    UnsafePathError,
    count_workspace_files,
    project_dir_for,
    validate_project_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


DEFAULT_STARTER_FILES = {
    "FastAPI + Python": {
        "app/__init__.py": "",
        "app/api/__init__.py": "",
        "app/main.py": """from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Microservice API", version="0.1.0")
app.include_router(router)


@app.get("/")
def read_root():
    return {"status": "online", "service": "FastAPI"}
""",
        "app/api/routes.py": """from fastapi import APIRouter

router = APIRouter()


@router.get("/items")
def get_items():
    return [{"id": 1, "name": "Item Alpha"}]
""",
        "requirements.txt": """fastapi>=0.115.0
uvicorn>=0.30.0
pydantic>=2.8.0
""",
        "README.md": """# FastAPI Starter Service
High-performance RESTful microservice built with FastAPI and Python 3.13.
""",
    },
    "Next.js + TypeScript": {
        "package.json": """{
  "name": "nextjs-starter",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build"
  }
}
""",
        "app/page.tsx": """export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <h1 className="text-3xl font-bold">StackPilot Next.js Application</h1>
    </main>
  );
}
""",
        "README.md": """# Next.js Starter
Modern web application built with Next.js 14 and TypeScript.
""",
    },
    "Go Microservice": {
        "main.go": """package main

import (
    "fmt"
    "net/http"
)

func main() {
    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "OK")
    })
    http.ListenAndServe(":8080", nil)
}
""",
        "go.mod": """module stackpilot/starter

go 1.22
""",
        "README.md": """# Go Microservice
Lightweight and concurrent microservice powered by Go.
""",
    },
}

TEMPLATE_LANGUAGES = {
    "FastAPI + Python": ["Python"],
    "Next.js + TypeScript": ["TypeScript", "React"],
    "Go Microservice": ["Go"],
}

DEFAULT_TEMPLATE = "FastAPI + Python"


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = ""
    source_type: str = Field("blank", pattern="^(blank|upload|git)$")
    template: Optional[str] = DEFAULT_TEMPLATE
    git_url: Optional[str] = None
    git_branch: Optional[str] = "main"

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        return validate_project_name(v)

    @field_validator("template")
    @classmethod
    def _known_template(cls, v: Optional[str]) -> str:
        if v is None:
            return DEFAULT_TEMPLATE
        if v not in DEFAULT_STARTER_FILES:
            raise ValueError(f"Unknown template '{v}'. Available: {', '.join(DEFAULT_STARTER_FILES)}.")
        return v


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    root_path: str
    is_indexed: bool
    languages: List[str]
    file_count: int  # measured on disk at request time, not the stored value
    workspace_exists: bool
    last_indexed: Optional[str] = None
    created_at: str


def to_response(p: Project) -> ProjectResponse:
    on_disk = count_workspace_files(p.root_path)
    return ProjectResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        root_path=p.root_path,
        is_indexed=p.is_indexed,
        languages=p.languages or [],
        file_count=on_disk or 0,
        workspace_exists=on_disk is not None,
        last_indexed=p.last_indexed_at.strftime("%Y-%m-%d %H:%M") if p.last_indexed_at else "Pending",
        created_at=p.created_at.isoformat(),
    )


def scaffold_starter_project(root_path: str, template: str) -> List[str]:
    """Write a template's starter files into root_path. Existing files are never overwritten."""
    os.makedirs(root_path, exist_ok=True)
    created_files = []

    for rel_path, content in DEFAULT_STARTER_FILES[template].items():
        full_path = os.path.join(root_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        created_files.append(rel_path)

    return created_files


@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List registered projects. Read-only: this never creates or modifies anything."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return [to_response(p) for p in result.scalars().all()]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new project workspace and scaffold the chosen template's starter files."""
    if payload.source_type != "blank":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Creating a project from source '{payload.source_type}' is not implemented yet.",
        )

    existing = (await db.execute(select(Project).where(Project.name == payload.name))).scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Project '{payload.name}' already exists.")

    try:
        proj_dir = project_dir_for(payload.name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # exist_ok=False makes folder creation atomic: we never adopt or write into a folder that
    # already holds someone's files (e.g. one left on disk after a project was unregistered).
    try:
        proj_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A workspace folder named '{payload.name}' already exists on disk.",
        )
    except OSError:
        logger.exception("Could not create workspace folder %s", proj_dir)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create workspace folder.")

    template = payload.template or DEFAULT_TEMPLATE
    try:
        scaffold_starter_project(str(proj_dir), template)
        project = Project(
            id=str(uuid.uuid4()),
            name=payload.name,
            description=payload.description or f"Project created with {template} starter.",
            root_path=str(proj_dir),
            is_indexed=False,
            languages=TEMPLATE_LANGUAGES[template],
            file_count=count_workspace_files(proj_dir) or 0,
            last_indexed_at=None,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
    except Exception:
        # Only the folder created a moment ago by this request is removed.
        await db.rollback()
        shutil.rmtree(proj_dir, ignore_errors=True)
        logger.exception("Project creation failed for '%s'", payload.name)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Project creation failed.")

    return to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project: Project = Depends(get_project_or_404)):
    """Retrieve details for a specific project by UUID or name."""
    return to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project: Project = Depends(get_project_or_404), db: AsyncSession = Depends(get_db)):
    """Unregister a project. Only the database record is removed; files on disk are preserved."""
    await db.delete(project)
    await db.commit()
    return None
