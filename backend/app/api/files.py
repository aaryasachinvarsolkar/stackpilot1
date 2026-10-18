import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_project_or_404
from app.config import settings
from app.models.project import Project
from app.services.workspace import (
    IGNORED_DIRS,
    IGNORED_FILES,
    PATH_ERROR_MESSAGE,
    UnsafePathError,
    resolve_in_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])

_BINARY_SNIFF_BYTES = 8192


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
    """Recursively scan a directory into TreeNodes. Symlinks are never followed or listed."""
    nodes: List[TreeNode] = []
    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
    except OSError:
        logger.warning("Could not scan directory %s", dir_path, exc_info=True)
        return nodes

    for entry in entries:
        if entry.name in IGNORED_DIRS or entry.name in IGNORED_FILES or entry.is_symlink():
            continue

        rel_path = os.path.relpath(entry.path, base_path).replace("\\", "/")

        if entry.is_dir(follow_symlinks=False):
            nodes.append(
                TreeNode(
                    name=entry.name,
                    path=rel_path,
                    type="directory",
                    children=scan_directory_tree(entry.path, base_path),
                )
            )
        else:
            try:
                size = entry.stat(follow_symlinks=False).st_size
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


def _workspace_root(project: Project) -> Path:
    """The project's folder on disk, or a 404 if it does not exist (no demo fallback)."""
    root = Path(project.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace folder for project '{project.name}' does not exist on disk.",
        )
    return root


def _safe_path(project_root: Path, relative_path: str) -> Path:
    try:
        return resolve_in_project(project_root, relative_path)
    except UnsafePathError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PATH_ERROR_MESSAGE)


@router.get("/tree", response_model=List[TreeNode])
async def get_file_tree(project: Project = Depends(get_project_or_404)):
    """Return the real directory tree of the project's workspace folder."""
    root = _workspace_root(project)
    return scan_directory_tree(str(root), str(root))


@router.get("/content", response_model=FileContentResponse)
async def get_file_content(
    path: str = Query(..., description="Relative file path"),
    project: Project = Depends(get_project_or_404),
):
    """Read a UTF-8 text file from the project's workspace folder."""
    root = _workspace_root(project)
    full_path = _safe_path(root, path)

    if not full_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{path}' not found.")

    try:
        size = full_path.stat().st_size
        if size > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,  # literal: the status constant was renamed across Starlette versions
                detail=f"File is {size} bytes; the limit is {settings.MAX_FILE_SIZE_BYTES} bytes.",
            )
        raw = full_path.read_bytes()
    except HTTPException:
        raise
    except OSError:
        logger.exception("Failed to read %s", full_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to read file.")

    if b"\x00" in raw[:_BINARY_SNIFF_BYTES]:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Binary files are not supported.")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File is not valid UTF-8 text."
        )

    rel = full_path.relative_to(root.resolve()).as_posix()
    return FileContentResponse(
        path=rel,
        file_name=full_path.name,
        content=content,
        line_count=len(content.splitlines()),
        language=detect_language(full_path.name),
    )


@router.put("/content", response_model=FileSaveResponse)
async def save_file_content(payload: FileSaveRequest, project: Project = Depends(get_project_or_404)):
    """Write a UTF-8 text file inside the project's workspace folder (atomic replace)."""
    root = _workspace_root(project)
    full_path = _safe_path(root, payload.path)

    data = payload.content.encode("utf-8")
    if len(data) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Content is {len(data)} bytes; the limit is {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )
    if full_path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path refers to a directory.")

    tmp_name: Optional[str] = None
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same folder, then atomically replace, so a failed write
        # can never leave a truncated file. Bytes are written verbatim (no newline translation).
        with tempfile.NamedTemporaryFile(dir=full_path.parent, delete=False, prefix=".sp-", suffix=".tmp") as tmp:
            tmp_name = tmp.name
            tmp.write(data)
        os.replace(tmp_name, full_path)
        tmp_name = None
    except OSError:
        logger.exception("Failed to write %s", full_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to write file.")
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)

    return FileSaveResponse(
        status="saved",
        path=full_path.relative_to(root.resolve()).as_posix(),
        bytes_written=len(data),
    )
