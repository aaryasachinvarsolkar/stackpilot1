"""Trusted helpers for everything that touches project folders on disk.

All path and project-name decisions live here so the API layer never builds a filesystem path
from user input by itself.
"""
import io
import logging
import os
import re
import shutil
import stat
import zipfile
import zlib
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

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


def detect_project_languages(project_root: str | Path) -> list[str]:
    """Inspect file extensions in workspace and return detected languages."""
    root = Path(project_root)
    if not root.is_dir():
        return ["Plaintext"]

    counts: dict[str, int] = {}
    ext_map = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP",
        ".html": "HTML",
        ".css": "CSS",
    }
    for _dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in ext_map:
                lang = ext_map[ext]
                counts[lang] = counts.get(lang, 0) + 1

    if not counts:
        return ["Plaintext"]
    sorted_langs = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [l[0] for l in sorted_langs[:4]]


class ArchiveError(ValueError):
    """The archive cannot be imported. The message is written for the client: it never carries raw exception text."""


class ArchiveTooLargeError(ArchiveError):
    """The archive, or what it would extract to, is over a configured limit."""


class GitUrlError(ValueError):
    """Not a plain GitHub repository URL."""


_ARCHIVE_NOT_ZIP = "The file is not a valid ZIP archive, or it is corrupt or uses an unsupported format."
_ARCHIVE_UNSAFE = "The archive contains an unsafe or unsupported entry, so nothing was imported."
_ARCHIVE_ENCRYPTED = "Encrypted archives are not supported."
_ZIP_READ_ERRORS = (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError)
_COPY_CHUNK = 64 * 1024
_MAX_PART_LENGTH = 255
_WINDOWS_INVALID_NAME_CHARS = set('<>"|?*')


def _safe_archive_parts(name: str, is_dir: bool) -> Optional[list[str]]:
    """The path parts of an archive entry name, or None if the name is unsafe on any supported system.

    Unsafe: empty, control characters (NUL included), absolute paths, any ':' (drive letters, NTFS streams), '..', empty or
    '.' parts, characters Windows forbids, trailing dots or spaces (Windows drops them), reserved device names, over-long names.
    """
    if not name or len(name) > _MAX_RELATIVE_PATH_LENGTH or any(ord(c) < 32 for c in name):
        return None
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        return None
    parts = normalized.split("/")
    if is_dir:
        parts = parts[:-1]  # the empty piece after the trailing slash
    if not parts:
        return None
    for part in parts:
        if part in ("", ".", "..") or len(part) > _MAX_PART_LENGTH or part != part.rstrip(" ."):
            return None
        if any(c in _WINDOWS_INVALID_NAME_CHARS for c in part):
            return None
        if part.split(".")[0].lower() in _WINDOWS_RESERVED:
            return None
    return parts


def _plan_archive(zf: zipfile.ZipFile, target_dir: Path) -> list[tuple[zipfile.ZipInfo, Path]]:
    """Check EVERY entry and return what to write. Touches nothing on disk; raises ArchiveError at the first problem."""
    infos = zf.infolist()
    if len(infos) > settings.MAX_ZIP_ENTRIES:
        raise ArchiveTooLargeError(f"The archive has more than {settings.MAX_ZIP_ENTRIES} entries.")

    entries: list[tuple[zipfile.ZipInfo, list[str]]] = []
    for info in infos:
        if info.flag_bits & 0x1:
            raise ArchiveError(_ARCHIVE_ENCRYPTED)
        kind = stat.S_IFMT(info.external_attr >> 16)  # 0 when the archive records no Unix mode
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):  # symlinks, devices, pipes, sockets
            logger.warning("Rejected archive: entry %r is not a regular file or folder", info.filename)
            raise ArchiveError(_ARCHIVE_UNSAFE)
        parts = _safe_archive_parts(info.filename, info.is_dir())
        if parts is None:
            logger.warning("Rejected archive: unsafe entry name %r", info.filename)
            raise ArchiveError(_ARCHIVE_UNSAFE)
        if not info.is_dir():
            entries.append((info, parts))

    # A single shared top-level folder (repo-main/...) is dropped, as GitHub archives have one.
    strip = bool(entries) and all(len(parts) > 1 and parts[0] == entries[0][1][0] for _, parts in entries)

    plan: list[tuple[zipfile.ZipInfo, Path]] = []
    file_keys: set[str] = set()
    folder_keys: set[str] = set()
    declared = 0
    for info, parts in entries:
        rel = parts[1:] if strip else parts
        if any(part in IGNORED_DIRS for part in rel):
            continue
        key = "/".join(rel).lower()
        if key in file_keys:  # same destination twice (case-insensitively: Windows treats them as one file)
            logger.warning("Rejected archive: duplicate entry %r", info.filename)
            raise ArchiveError(_ARCHIVE_UNSAFE)
        file_keys.add(key)
        folder_keys.update("/".join(rel[:i]).lower() for i in range(1, len(rel)))
        dest = target_dir.joinpath(*rel).resolve()
        if dest == target_dir or not dest.is_relative_to(target_dir):
            logger.warning("Rejected archive: entry %r resolves outside the workspace", info.filename)
            raise ArchiveError(_ARCHIVE_UNSAFE)
        declared += info.file_size
        plan.append((info, dest))

    if file_keys & folder_keys:  # a name used both as a file and as a folder
        raise ArchiveError(_ARCHIVE_UNSAFE)
    if declared > settings.MAX_ZIP_UNCOMPRESSED_BYTES:
        raise ArchiveTooLargeError(f"The archive would extract to more than {settings.MAX_ZIP_UNCOMPRESSED_BYTES} bytes.")
    return plan


def extract_zip_archive(zip_bytes: bytes, target_dir: Path) -> int:
    """Safely extract ZIP bytes into target_dir and return the number of files written.

    Every entry is validated before the first byte is written, and one unsafe entry rejects the whole archive. The
    total size is checked on what is really extracted, not only on what the archive declares. If anything fails,
    whatever this call created is removed again. Strips a single shared top-level folder (repo-main/...).
    """
    target_dir = Path(target_dir).resolve()
    created = not target_dir.exists()
    written: list[Path] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            plan = _plan_archive(zf, target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            total = 0
            for info, dest in plan:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, open(dest, "xb") as target:  # "x": never overwrite
                    written.append(dest)
                    while chunk := source.read(_COPY_CHUNK):
                        total += len(chunk)
                        if total > settings.MAX_ZIP_UNCOMPRESSED_BYTES:
                            raise ArchiveTooLargeError(
                                f"The archive extracts to more than {settings.MAX_ZIP_UNCOMPRESSED_BYTES} bytes."
                            )
                        target.write(chunk)
            return len(plan)
    except BaseException as exc:
        if created:
            shutil.rmtree(target_dir, ignore_errors=True)
        else:
            for path in written:
                path.unlink(missing_ok=True)
        if isinstance(exc, _ZIP_READ_ERRORS):
            raise ArchiveError(_ARCHIVE_NOT_ZIP) from exc
        raise


_GITHUB_SEGMENT = r"[A-Za-z0-9_.-]{1,100}"
_GITHUB_URL = re.compile(
    rf"^(?:(?:https?://)?(?:www\.)?github\.com/|git@github\.com:)(?P<owner>{_GITHUB_SEGMENT})/(?P<repo>{_GITHUB_SEGMENT})/?$",
    re.IGNORECASE,
)


def parse_github_url(url: str) -> tuple[str, str]:
    """(owner, repository) of a plain GitHub repository URL, or GitUrlError.

    Accepts https://github.com/owner/repo, with or without a trailing '/' or '.git', http:// or no scheme, www., and
    git@github.com:owner/repo.git. Only a literal '.git' suffix is removed (not any trailing '.', 'g', 'i', 't'). Anything
    else, such as extra path parts (/tree/main), queries, other hosts or '.'/'..' names, is refused.
    """
    match = _GITHUB_URL.fullmatch(url.strip()) if isinstance(url, str) else None
    if not match:
        raise GitUrlError("Invalid GitHub URL. Format must be: https://github.com/owner/repository")
    owner, repo = match.group("owner"), match.group("repo")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if owner in (".", "..") or repo in ("", ".", ".."):
        raise GitUrlError("Invalid GitHub URL. Format must be: https://github.com/owner/repository")
    return owner, repo


def build_project_graph(project_root: str | Path) -> dict:
    """Analyze real project files and construct a dependency/architecture graph.

    Returns nodes, links, and layer summaries.
    """
    root = Path(project_root).resolve()
    if not root.is_dir():
        return {"nodes": [], "links": [], "summary": "Empty project"}

    nodes = []
    links = []
    node_ids = set()

    for _dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for f in filenames:
            if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".json")):
                full_path = os.path.join(_dirpath, f)
                rel_path = os.path.relpath(full_path, root).replace("\\", "/")

                # Categorize node
                lower_p = rel_path.lower()
                if "main" in lower_p or "app." in lower_p or "index" in lower_p or "server" in lower_p:
                    node_type = "entry"
                elif "api" in lower_p or "route" in lower_p or "controller" in lower_p:
                    node_type = "api"
                elif "model" in lower_p or "schema" in lower_p or "entity" in lower_p:
                    node_type = "model"
                elif "service" in lower_p or "core" in lower_p or "util" in lower_p or "lib" in lower_p:
                    node_type = "service"
                elif "component" in lower_p or "view" in lower_p:
                    node_type = "component"
                else:
                    node_type = "module"

                node_id = rel_path
                node_ids.add(node_id)
                nodes.append({
                    "id": node_id,
                    "label": f,
                    "path": rel_path,
                    "type": node_type,
                })

                # Try scanning import statements for links
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                    for line in lines[:80]:
                        s = line.strip()
                        # Python: from app.api import routes / from .database import get_db
                        if s.startswith("from ") or s.startswith("import "):
                            target_match = re.search(r"(?:from\s+([.\w]+)|import\s+([.\w]+))", s)
                            if target_match:
                                target_raw = (target_match.group(1) or target_match.group(2) or "").replace(".", "/")
                                for existing_id in list(node_ids):
                                    if target_raw and (target_raw in existing_id or existing_id in target_raw) and existing_id != node_id:
                                        links.append({
                                            "source": node_id,
                                            "target": existing_id,
                                            "type": "import",
                                        })
                        # JS/TS: import ... from './...'
                        elif s.startswith("import ") and "from" in s:
                            ts_match = re.search(r"from\s+['\"]([./\w-]+)['\"]", s)
                            if ts_match:
                                raw_sub = ts_match.group(1).lstrip("./")
                                for existing_id in list(node_ids):
                                    if raw_sub and raw_sub in existing_id and existing_id != node_id:
                                        links.append({
                                            "source": node_id,
                                            "target": existing_id,
                                            "type": "import",
                                        })
                except Exception:
                    pass

    # Deduplicate links
    dedup_links = []
    seen = set()
    for l in links:
        key = (l["source"], l["target"])
        if key not in seen:
            seen.add(key)
            dedup_links.append(l)

    return {
        "nodes": nodes[:60],
        "links": dedup_links[:80],
        "summary": f"Analyzed {len(nodes)} modules with {len(dedup_links)} dependency connections",
    }

