"""Trusted helpers for everything that touches project folders on disk.

All path and project-name decisions live here so the API layer never builds a filesystem path
from user input by itself.
"""
import os
import re
from pathlib import Path
from typing import Optional

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]

PATH_ERROR_MESSAGE = "Illegal file path. Path traversal is strictly prohibited."

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

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_MAX_RELATIVE_PATH_LENGTH = 1024


class UnsafePathError(ValueError):
    """The requested path or name would leave its allowed location."""


def workspaces_root() -> Path:
    configured = (settings.WORKSPACES_ROOT or "").strip()
    return (Path(configured) if configured else BACKEND_DIR / "workspaces").resolve()


def validate_project_name(name: str) -> str:
    """Return the name unchanged if it is safe to use as a folder name, else raise ValueError."""
    if not isinstance(name, str) or not PROJECT_NAME_PATTERN.match(name):
        raise ValueError(
            "Project name must be 1-100 characters: letters, digits, '.', '_' or '-', "
            "starting with a letter or digit (no spaces or slashes)."
        )
    if name.endswith("."):
        raise ValueError("Project name must not end with a dot.")
    if name.split(".")[0].lower() in _WINDOWS_RESERVED:
        raise ValueError("Project name is a reserved system name.")
    return name


def project_dir_for(name: str) -> Path:
    """Folder for a new project; guaranteed to be a direct child of the workspaces root."""
    try:
        validate_project_name(name)
    except ValueError as exc:
        raise UnsafePathError(str(exc)) from exc
    root = workspaces_root()
    target = (root / name).resolve()
    if target.parent != root:
        raise UnsafePathError(PATH_ERROR_MESSAGE)
    return target


def resolve_in_project(project_root: str | Path, relative_path: str) -> Path:
    """Resolve a user-supplied relative path to an absolute path strictly inside project_root.

    Rejects absolute paths, drive letters / alternate streams (any ':'), '..' components,
    NUL bytes, empty paths and anything that resolves (symlinks included) outside the root.
    """
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
        raise UnsafePathError(PATH_ERROR_MESSAGE)
    if len(relative_path) > _MAX_RELATIVE_PATH_LENGTH:
        raise UnsafePathError(PATH_ERROR_MESSAGE)

    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        raise UnsafePathError(PATH_ERROR_MESSAGE)
    parts = normalized.split("/")
    if ".." in parts:
        raise UnsafePathError(PATH_ERROR_MESSAGE)
    parts = [p for p in parts if p not in ("", ".")]
    if not parts:
        raise UnsafePathError(PATH_ERROR_MESSAGE)

    root = Path(project_root).resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise UnsafePathError(PATH_ERROR_MESSAGE)
    return candidate


def count_workspace_files(project_root: str | Path) -> Optional[int]:
    """Number of regular files under the project folder (ignored dirs/files and symlinks skipped).

    Returns None if the folder does not exist.
    """
    root = Path(project_root)
    if not root.is_dir():
        return None
    total = 0
    for _dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not os.path.islink(os.path.join(_dirpath, d))]
        total += sum(
            1
            for f in filenames
            if f not in IGNORED_FILES and not os.path.islink(os.path.join(_dirpath, f))
        )
    return total
