import os
import uuid
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models.project import Project, ProjectFile

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    source_type: str = Field("blank", pattern="^(blank|upload|git)$")
    template: Optional[str] = "FastAPI + Python"
    git_url: Optional[str] = None
    git_branch: Optional[str] = "main"


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    root_path: str
    is_indexed: bool
    languages: List[str]
    file_count: int
    last_indexed: Optional[str] = None
    created_at: str


DEFAULT_STARTER_FILES = {
    "FastAPI + Python": {
        "app/main.py": """from fastapi import FastAPI

app = FastAPI(title="Microservice API", version="0.1.0")

@app.get("/")
def read_root():
    return {"status": "online", "service": "FastAPI"}
""",
        "app/api/routes.py": """from fastapi import APIRouter

router = APIRouter()

@app.get("/items")
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


def scaffold_starter_project(root_path: str, template: str) -> List[str]:
    """Write starter files for a template into the project root path."""
    os.makedirs(root_path, exist_ok=True)
    file_map = DEFAULT_STARTER_FILES.get(template, DEFAULT_STARTER_FILES["FastAPI + Python"])
    created_files = []

    for rel_path, content in file_map.items():
        full_path = os.path.join(root_path, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        created_files.append(rel_path)

    return created_files


@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all registered projects. Auto-seeds defaults if table is empty."""
    stmt = select(Project).order_by(Project.created_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Seed default sample projects if database has 0 projects
    if not projects:
        default_defs = [
            {
                "name": "task-manager-service",
                "description": "Distributed task orchestrator with FastAPI backend and async worker pool",
                "languages": ["Python", "SQLAlchemy", "AsyncPG"],
                "file_count": 24,
            },
            {
                "name": "auth-microservice",
                "description": "OAuth2 / JWT token authentication service with Redis session store",
                "languages": ["TypeScript", "Next.js", "Redis"],
                "file_count": 18,
            },
            {
                "name": "e-commerce-api",
                "description": "High-throughput checkout API with Stripe webhook integrations",
                "languages": ["Go", "PostgreSQL", "Docker"],
                "file_count": 42,
            },
        ]
        seeded = []
        for d in default_defs:
            proj_dir = os.path.abspath(os.path.join(os.getcwd(), "workspaces", d["name"]))
            p = Project(
                id=str(uuid.uuid4()),
                name=d["name"],
                description=d["description"],
                root_path=proj_dir,
                is_indexed=True,
                languages=d["languages"],
                file_count=d["file_count"],
                last_indexed_at=datetime.now(timezone.utc),
            )
            db.add(p)
            seeded.append(p)
        await db.commit()
        for p in seeded:
            await db.refresh(p)
        projects = seeded

    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            root_path=p.root_path,
            is_indexed=p.is_indexed,
            languages=p.languages or [],
            file_count=p.file_count,
            last_indexed=p.last_indexed_at.strftime("%Y-%m-%d %H:%M") if p.last_indexed_at else "Pending",
            created_at=p.created_at.isoformat(),
        )
        for p in projects
    ]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new project workspace and scaffold initial template files."""
    # Check if a project with the same name already exists
    stmt = select(Project).where(Project.name == payload.name)
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project '{payload.name}' already exists.",
        )

    # Establish workspace directory
    proj_dir = os.path.abspath(os.path.join(os.getcwd(), "workspaces", payload.name))
    template_name = payload.template or "FastAPI + Python"
    created_files = scaffold_starter_project(proj_dir, template_name)

    # Determine languages
    if "Python" in template_name:
        langs = ["Python"]
    elif "Next.js" in template_name:
        langs = ["TypeScript", "React"]
    elif "Go" in template_name:
        langs = ["Go"]
    else:
        langs = ["Plaintext"]

    project = Project(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description or f"Project created with {template_name} starter.",
        root_path=proj_dir,
        is_indexed=False,
        languages=langs,
        file_count=len(created_files),
        last_indexed_at=None,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        is_indexed=project.is_indexed,
        languages=project.languages,
        file_count=project.file_count,
        last_indexed=None,
        created_at=project.created_at.isoformat(),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve details for a specific project by UUID or Name."""
    # Try by UUID first
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalars().first()
    if not project:
        # Fallback search by name
        stmt = select(Project).where(Project.name == project_id)
        project = (await db.execute(stmt)).scalars().first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        is_indexed=project.is_indexed,
        languages=project.languages or [],
        file_count=project.file_count,
        last_indexed=project.last_indexed_at.strftime("%Y-%m-%d %H:%M") if project.last_indexed_at else "Pending",
        created_at=project.created_at.isoformat(),
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a project from the registry."""
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalars().first()
    if not project:
        stmt = select(Project).where(Project.name == project_id)
        project = (await db.execute(stmt)).scalars().first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await db.delete(project)
    await db.commit()
    return None
