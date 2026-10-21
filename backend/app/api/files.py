import hashlib
import logging
import os
import re
import tempfile
import threading
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
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_HASH_CHUNK_BYTES = 1024 * 1024

# Saves are check-then-write, so they run one at a time inside this process. (Another process writing
# the same file at the same instant is not covered by this lock; see replace_existing_file.)
_save_lock = threading.Lock()


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
    # SHA-256 (lowercase hex) of the exact bytes on disk. A save must send it back as base_sha256.
    sha256: str


class FileSaveRequest(BaseModel):
    path: str
    content: str
    # The `sha256` returned when the content was loaded. Required, but declared optional here so that a
    # missing value is answered with a clear 428 after the path and size checks rather than a generic 422.
    base_sha256: Optional[str] = None


class FileSaveResponse(BaseModel):
    status: str
    path: str
    bytes_written: int
    sha256: str


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


class FileMissingError(Exception):
    """The file to update does not exist (it was never there, or it was deleted)."""


class FileChangedError(Exception):
    """The file on disk no longer has the content the caller based its edit on."""


def sha256_of_file(path: Path) -> str:
    """SHA-256 (lowercase hex) of a file's raw bytes, read in chunks so size never matters for memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_unchanged(full_path: Path, base_sha256: str) -> None:
    try:
        current = sha256_of_file(full_path)
    except (FileNotFoundError, NotADirectoryError):
        raise FileMissingError() from None
    if current != base_sha256:
        raise FileChangedError()


def replace_existing_file(full_path: Path, data: bytes, base_sha256: str) -> str:
    """Overwrite an EXISTING file, but only if its bytes still hash to `base_sha256`.

    Never creates a file or a folder. The bytes are written to a temporary file next to the target and
    then swapped in atomically, so a failure cannot leave a truncated file; the temporary file is always
    removed. The disk is hashed once before anything is written and again right before the swap.
    Raises FileMissingError / FileChangedError without having changed any bytes of the target.
    Returns the SHA-256 of the new content.

    Limit: the lock and the second check narrow the check-then-write window to the instant between the
    second check and os.replace; a different process changing the same file in exactly that instant can
    still win, and there is no portable way to make "replace only if unchanged" fully atomic.
    """
    base_sha256 = base_sha256.lower()
    tmp_name: Optional[str] = None
    with _save_lock:
        try:
            _require_unchanged(full_path, base_sha256)
            with tempfile.NamedTemporaryFile(dir=full_path.parent, delete=False, prefix=".sp-", suffix=".tmp") as tmp:
                tmp_name = tmp.name
                tmp.write(data)
            _require_unchanged(full_path, base_sha256)
            os.replace(tmp_name, full_path)
            tmp_name = None
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
    return hashlib.sha256(data).hexdigest()


def _checked_base_sha256(value: Optional[str]) -> str:
    if value is None:
        raise HTTPException(
            status_code=428,  # literal: the status constant name differs across Starlette versions
            detail=(
                "base_sha256 is required: send the sha256 of the content you loaded "
                "(returned by GET .../files/content). Nothing was written."
            ),
        )
    if not isinstance(value, str) or not _SHA256_PATTERN.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_sha256 must be exactly 64 hexadecimal characters. Nothing was written.",
        )
    return value.lower()


def _missing_file_error(path: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"File '{path}' does not exist. This endpoint only updates existing files; "
            "it never creates files or folders. Nothing was written."
        ),
    )


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
        sha256=hashlib.sha256(raw).hexdigest(),
    )


@router.put("/content", response_model=FileSaveResponse)
async def save_file_content(payload: FileSaveRequest, project: Project = Depends(get_project_or_404)):
    """Replace the content of an EXISTING UTF-8 text file, if it has not changed since it was loaded.

    Checks run in this order, and every rejection leaves the disk untouched: unknown project 404,
    project folder missing 404, unsafe path 400, content too large 413, base_sha256 missing 428,
    base_sha256 malformed 400, path is a directory 400, file does not exist 404 (nothing is ever
    created, not even a parent folder), disk content differs from base_sha256 409.
    """
    root = _workspace_root(project)
    full_path = _safe_path(root, payload.path)

    data = payload.content.encode("utf-8")
    if len(data) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Content is {len(data)} bytes; the limit is {settings.MAX_FILE_SIZE_BYTES} bytes.",
        )
    base_sha256 = _checked_base_sha256(payload.base_sha256)
    if full_path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path refers to a directory.")
    if not full_path.is_file():
        raise _missing_file_error(payload.path)

    try:
        new_sha256 = replace_existing_file(full_path, data, base_sha256)
    except FileMissingError:
        raise _missing_file_error(payload.path)
    except FileChangedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The file changed on disk since it was loaded, so it was not overwritten. "
                "Nothing was written. Reload the file to see its current content."
            ),
        )
    except OSError:
        logger.exception("Failed to write %s", full_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to write file.")

    return FileSaveResponse(
        status="saved",
        path=full_path.relative_to(root.resolve()).as_posix(),
        bytes_written=len(data),
        sha256=new_sha256,
    )
