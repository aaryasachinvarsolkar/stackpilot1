import io
import logging
import os
import shutil
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_or_404
from app.database import get_db
from app.models.project import Project
from app.config import settings
from app.services.workspace import (
    ArchiveError,
    ArchiveTooLargeError,
    GitUrlError,
    UnsafePathError,
    count_workspace_files,
    project_dir_for,
    validate_project_name,
    detect_project_languages,
    extract_zip_archive,
    build_project_graph,
    parse_github_url,
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
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.2.15",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/node": "^20.14.0",
    "@types/react": "^18.3.0",
    "typescript": "^5.5.0"
  }
}
""",
        "tsconfig.json": """{
  "compilerOptions": {
    "target": "es2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
""",
        "app/layout.tsx": """import type { ReactNode } from "react";

export const metadata = { title: "StackPilot Next.js Application" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
""",
        "app/page.tsx": """export default function HomePage() {
  return (
    <main style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", padding: 32, fontFamily: "sans-serif" }}>
      <h1>StackPilot Next.js Application</h1>
    </main>
  );
}
""",
        "README.md": """# Next.js Starter
Modern web application built with Next.js 14 and TypeScript.
Run it from StackPilot's "Run in Browser" tab, or with `npm install` then `npm run dev`.
""",
    },
    "Go Microservice": {
        "main.go": """package main

import (
    "fmt"
    "net/http"
    "os"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }
    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "OK")
    })
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprint(w, `{"status":"online","service":"Go"}`)
    })
    http.ListenAndServe(":"+port, nil)
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
    origin: str  # unclassified | user | import | upload | git | seed
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
        origin=p.origin,
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

    existing = (
        (await db.execute(select(Project).where(func.lower(Project.name) == payload.name.lower()))).scalars().first()
    )
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
            origin="user",
            languages=TEMPLATE_LANGUAGES[template],
            file_count=count_workspace_files(proj_dir) or 0,
            last_indexed_at=None,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
    except IntegrityError:
        # Lost a race with a concurrent request that registered the same name (unique index).
        await db.rollback()
        shutil.rmtree(proj_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Project '{payload.name}' already exists.")
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


class GitImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    git_url: str = Field(..., min_length=3)
    branch: Optional[str] = "main"
    description: Optional[str] = ""

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        try:
            return validate_project_name(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


_READ_CHUNK = 1024 * 1024
_IMPORT_FAILED = "The project could not be imported."


def _too_large(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"The {what} is larger than the {settings.MAX_UPLOAD_BYTES} byte limit.",
    )


async def _read_upload_limited(file: UploadFile) -> bytes:
    """Read an upload in chunks and stop as soon as it passes MAX_UPLOAD_BYTES (counted on the bytes really read)."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > settings.MAX_UPLOAD_BYTES:
            raise _too_large("upload")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_or_raise(zip_bytes: bytes, proj_dir) -> int:
    """Extract an archive into proj_dir; every failure becomes a client-safe HTTP error and leaves no folder behind."""
    try:
        return extract_zip_archive(zip_bytes, proj_dir)
    except ArchiveTooLargeError as exc:
        shutil.rmtree(proj_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    except ArchiveError as exc:
        shutil.rmtree(proj_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        shutil.rmtree(proj_dir, ignore_errors=True)
        logger.exception("Unexpected failure while extracting an archive into %s", proj_dir)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_IMPORT_FAILED)


@router.post("/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def upload_project_zip(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a ZIP archive and create a project workspace from its contents."""
    try:
        clean_name = validate_project_name(name.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    existing = (
        (await db.execute(select(Project).where(func.lower(Project.name) == clean_name.lower()))).scalars().first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Project '{clean_name}' already exists.")

    try:
        proj_dir = project_dir_for(clean_name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if proj_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A workspace folder named '{clean_name}' already exists on disk.",
        )

    zip_bytes = await _read_upload_limited(file)
    if not zip_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    extracted_count = _extract_or_raise(zip_bytes, proj_dir)
    try:
        langs = detect_project_languages(proj_dir)
        total_files = count_workspace_files(proj_dir) or extracted_count

        project = Project(
            id=str(uuid.uuid4()),
            name=clean_name,
            description=description or f"Imported from uploaded ZIP archive ({file.filename}).",
            root_path=str(proj_dir),
            is_indexed=False,
            origin="upload",
            languages=langs,
            file_count=total_files,
            last_indexed_at=None,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return to_response(project)
    except Exception as exc:
        shutil.rmtree(proj_dir, ignore_errors=True)
        await db.rollback()
        logger.exception("Failed to import uploaded project %s", clean_name)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_IMPORT_FAILED)


@router.post("/git", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def import_git_project(
    payload: GitImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Clone/import a project from a public GitHub repository link."""
    clean_name = payload.name.strip()
    existing = (
        (await db.execute(select(Project).where(func.lower(Project.name) == clean_name.lower()))).scalars().first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Project '{clean_name}' already exists.")

    try:
        proj_dir = project_dir_for(clean_name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if proj_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A workspace folder named '{clean_name}' already exists on disk.",
        )

    try:
        owner, repo = parse_github_url(payload.git_url)
    except GitUrlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    branch = payload.branch or "main"

    # Try downloading the repository zip archive (at most MAX_UPLOAD_BYTES, counted on the bytes actually received)
    zip_bytes = None
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        for b in [branch, "master", "main"]:
            archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{b}.zip"
            try:
                async with client.stream("GET", archive_url) as r:
                    if r.status_code != 200:
                        continue
                    declared = r.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > settings.MAX_UPLOAD_BYTES:
                        raise _too_large("repository archive")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in r.aiter_bytes():
                        total += len(chunk)
                        if total > settings.MAX_UPLOAD_BYTES:
                            raise _too_large("repository archive")
                        chunks.append(chunk)
                    if total > 100:
                        zip_bytes = b"".join(chunks)
                        break
            except HTTPException:
                raise
            except Exception as e:
                logger.debug(f"Failed fetching {archive_url}: {e}")

    if not zip_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not download repository archive from GitHub ({owner}/{repo}). Verify it is a public repository.",
        )

    extracted_count = _extract_or_raise(zip_bytes, proj_dir)
    try:
        langs = detect_project_languages(proj_dir)
        total_files = count_workspace_files(proj_dir) or extracted_count

        project = Project(
            id=str(uuid.uuid4()),
            name=clean_name,
            description=payload.description or f"Imported from GitHub: {owner}/{repo}",
            root_path=str(proj_dir),
            is_indexed=False,
            origin="git",
            languages=langs,
            file_count=total_files,
            last_indexed_at=None,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return to_response(project)
    except Exception as exc:
        shutil.rmtree(proj_dir, ignore_errors=True)
        await db.rollback()
        logger.exception("Failed to import git project %s", clean_name)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_IMPORT_FAILED)


@router.get("/{project_id}/graph")
async def get_project_graph(project: Project = Depends(get_project_or_404)):
    """Generate architecture and module dependency graph for the project."""
    return build_project_graph(project.root_path)

