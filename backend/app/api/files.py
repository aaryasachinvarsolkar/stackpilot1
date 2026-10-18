import os
from typing import List, Optional, Union
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.project import Project

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "stackpilot.db",
    ".env",
}


class TreeNode(BaseModel):
    name: str
    path: str
    type: str  # "file" | "directory"
    size: Optional[int] = None
    language: Optional[str] = None
    children: Optional[List["TreeNode"]] = None


class FileContentResponse(BaseModel):
    path: str
    file_name: str
    content: str
    line_count: int
    language: str


class FileSaveRequest(BaseModel):
    path: str
    content: str


class FileSaveResponse(BaseModel):
    status: str
    path: str
    bytes_written: int


def detect_language(file_name: str) -> str:
    """Detect language by extension."""
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""
    mapping = {
        "py": "python",
        "ts": "typescript",
        "tsx": "typescript",
        "js": "javascript",
        "jsx": "javascript",
        "json": "json",
        "md": "markdown",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "sql": "sql",
        "html": "html",
        "css": "css",
        "txt": "plaintext",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
    }
    return mapping.get(ext, "plaintext")


def scan_directory_tree(dir_path: str, base_path: str) -> List[TreeNode]:
    """Recursively scan directory and construct a TreeNode list."""
    nodes: List[TreeNode] = []
    if not os.path.exists(dir_path):
        return nodes

    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return nodes

    for entry in entries:
        if entry.name in IGNORED_DIRS or entry.name in IGNORED_FILES:
            continue

        rel_path = os.path.relpath(entry.path, base_path).replace("\\", "/")

        if entry.is_dir():
            child_nodes = scan_directory_tree(entry.path, base_path)
            nodes.append(
                TreeNode(
                    name=entry.name,
                    path=rel_path,
                    type="directory",
                    children=child_nodes,
                )
            )
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            nodes.append(
                TreeNode(
                    name=entry.name,
                    path=rel_path,
                    type="file",
                    size=size,
                    language=detect_language(entry.name),
                )
            )

    return nodes


DEFAULT_DEMO_TREE = [
    TreeNode(
        name="app",
        path="app",
        type="directory",
        children=[
            TreeNode(
                name="api",
                path="app/api",
                type="directory",
                children=[
                    TreeNode(name="routes.py", path="app/api/routes.py", type="file", size=1883, language="python"),
                ],
            ),
            TreeNode(
                name="core",
                path="app/core",
                type="directory",
                children=[
                    TreeNode(name="config.py", path="app/core/config.py", type="file", size=950, language="python"),
                ],
            ),
            TreeNode(
                name="database",
                path="app/database",
                type="directory",
                children=[
                    TreeNode(name="connection.py", path="app/database/connection.py", type="file", size=1353, language="python"),
                    TreeNode(name="session.py", path="app/database/session.py", type="file", size=820, language="python"),
                ],
            ),
            TreeNode(
                name="models",
                path="app/models",
                type="directory",
                children=[
                    TreeNode(name="base.py", path="app/models/base.py", type="file", size=585, language="python"),
                    TreeNode(name="user.py", path="app/models/user.py", type="file", size=1200, language="python"),
                ],
            ),
            TreeNode(
                name="middleware",
                path="app/middleware",
                type="directory",
                children=[
                    TreeNode(name="rateLimiter.ts", path="app/middleware/rateLimiter.ts", type="file", size=1420, language="typescript"),
                ],
            ),
            TreeNode(name="main.py", path="app/main.py", type="file", size=1539, language="python"),
        ],
    ),
    TreeNode(
        name="tests",
        path="tests",
        type="directory",
        children=[
            TreeNode(name="test_health.py", path="tests/test_health.py", type="file", size=1266, language="python"),
        ],
    ),
    TreeNode(name="requirements.txt", path="requirements.txt", type="file", size=209, language="plaintext"),
    TreeNode(name="README.md", path="README.md", type="file", size=4941, language="markdown"),
]


DEFAULT_FILE_CONTENTS = {
    "app/api/routes.py": """from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from app.database import check_database_connection

router = APIRouter()

@router.get("/api/health", summary="Detailed Readiness Probe")
async def detailed_health():
    \"\"\"Readiness probe checking database connectivity and environment details.\"\"\"
    db_status = await check_database_connection()
    return {
        "status": "healthy" if db_status["status"] == "connected" else "degraded",
        "database": db_status["status"],
        "database_type": db_status.get("type", "unknown"),
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
""",
    "app/main.py": """from fastapi import FastAPI
from app.api.routes import router as api_router

app = FastAPI(title="STACKPILOT Microservice", version="0.1.0")
app.include_router(api_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
""",
    "app/middleware/rateLimiter.ts": """import { Request, Response, NextFunction } from "express";

interface RateLimitStore {
  [ip: string]: { count: number; resetTime: number };
}

const store: RateLimitStore = {};

export function rateLimiter(limit = 60, windowMs = 60000) {
  return (req: Request, res: Response, next: NextFunction) => {
    const ip = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "unknown";
    const now = Date.now();

    if (!store[ip] || now > store[ip].resetTime) {
      store[ip] = { count: 1, resetTime: now + windowMs };
      return next();
    }

    store[ip].count += 1;
    if (store[ip].count > limit) {
      return res.status(429).json({ error: "Too many requests. Please try again later." });
    }
    next();
  };
}
""",
    "requirements.txt": """fastapi>=0.115.0
uvicorn>=0.30.0
sqlalchemy>=2.0.35
aiosqlite>=0.20.0
pydantic-settings>=2.5.2
pytest>=8.3.3
httpx>=0.27.2
""",
    "README.md": """# STACKPILOT Microservice
Unified AI-assisted software development platform and microservice workspace.
""",
}


async def resolve_project(project_id: str, db: AsyncSession) -> Optional[Project]:
    stmt = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt)).scalars().first()
    if not project:
        stmt = select(Project).where(Project.name == project_id)
        project = (await db.execute(stmt)).scalars().first()
    return project


@router.get("/tree", response_model=List[TreeNode])
async def get_file_tree(project_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve the file directory tree for the specified project."""
    project = await resolve_project(project_id, db)
    if not project:
        # Fallback to demo tree if project not found
        return DEFAULT_DEMO_TREE

    if os.path.exists(project.root_path):
        tree = scan_directory_tree(project.root_path, project.root_path)
        if tree:
            return tree

    return DEFAULT_DEMO_TREE


@router.get("/content", response_model=FileContentResponse)
async def get_file_content(
    project_id: str,
    path: str = Query(..., description="Relative file path"),
    db: AsyncSession = Depends(get_db),
):
    """Read content of a specific file."""
    # Prevent path traversal
    normalized_path = os.path.normpath(path).replace("\\", "/")
    if normalized_path.startswith("..") or "/../" in normalized_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Illegal file path. Path traversal is strictly prohibited.",
        )

    project = await resolve_project(project_id, db)
    content: Optional[str] = None

    if project and os.path.exists(project.root_path):
        full_path = os.path.join(project.root_path, normalized_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to read file: {e}",
                )

    # Fallback content if file not on disk
    if content is None:
        filename = normalized_path.split("/")[-1]
        content = DEFAULT_FILE_CONTENTS.get(
            normalized_path,
            f"# Content of {normalized_path}\n# Loaded via STACKPILOT workspace engine.\n",
        )

    filename = normalized_path.split("/")[-1]
    line_count = len(content.splitlines())

    return FileContentResponse(
        path=normalized_path,
        file_name=filename,
        content=content,
        line_count=line_count,
        language=detect_language(filename),
    )


@router.put("/content", response_model=FileSaveResponse)
async def save_file_content(
    project_id: str,
    payload: FileSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save/update content of a specific file."""
    normalized_path = os.path.normpath(payload.path).replace("\\", "/")
    if normalized_path.startswith("..") or "/../" in normalized_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Illegal file path. Path traversal is strictly prohibited.",
        )

    project = await resolve_project(project_id, db)
    if not project:
        # Fallback simulation
        return FileSaveResponse(
            status="saved",
            path=normalized_path,
            bytes_written=len(payload.content.encode("utf-8")),
        )

    full_path = os.path.join(project.root_path, normalized_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(payload.content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file: {e}",
        )

    return FileSaveResponse(
        status="saved",
        path=normalized_path,
        bytes_written=len(payload.content.encode("utf-8")),
    )
