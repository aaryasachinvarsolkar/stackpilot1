import asyncio
import fnmatch
import hashlib
import logging
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_parser import detect_language, parse_source
from app.models.code_chunk import CodeChunk
from app.models.project import Project, ProjectFile

import re
from app.services.workspace import IGNORED_DIRS, IGNORED_FILES, resolve_in_project

logger = logging.getLogger(__name__)

_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})
_PROHIBITED_PATTERNS = (
    "secrets*", "*.secrets", "*.secret",
    "secret.json", "secret.yml", "secret.yaml", "secret.toml", "secret.ini", "secret.txt", "secret.cfg",
    "credentials*", "credential.json", "credential.yml", "credential.yaml",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.ppk", "*.p8", "*.kdbx", "*.gpg", "*.asc",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".htpasswd", ".git-credentials", ".pgpass", ".dockercfg", ".dockerconfigjson",
    "*.tfvars", "*.tfstate", "*.tfstate.*", "kubeconfig", "*.kubeconfig",
    "service-account*.json", "serviceaccount*.json", "client_secret*.json",
)
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_lines(text: str) -> List[str]:
    return _LINE_BREAK.split(text)


def is_prohibited_file_name(name: str) -> bool:
    lowered = name.lower()
    if lowered == ".env" or lowered.endswith(".env"):
        return True
    if lowered.startswith(".env.") and lowered not in _ENV_TEMPLATES:
        return True
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in _PROHIBITED_PATTERNS)


# --- Limits --------------------------------------------------------------------------------------
MAX_INDEX_FILE_SIZE_BYTES = 512 * 1024  # 512 KB per file
MAX_INDEX_FILES = 2_000  # max supported files in one project scan
MAX_INDEX_TOTAL_BYTES = 20 * 1024 * 1024  # 20 MB total scanned content
SUPPORTED_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".go"})

_EXTRA_IGNORED_DIRS = frozenset({
    ".mypy_cache", ".ruff_cache", ".tox", ".gradle", ".terraform", ".cache",
    ".nuxt", ".svelte-kit", ".parcel-cache", "coverage", "htmlcov", "site-packages",
})
_ALL_IGNORED_DIRS = frozenset(d.lower() for d in IGNORED_DIRS) | _EXTRA_IGNORED_DIRS
_ALL_IGNORED_FILES = frozenset(f.lower() for f in IGNORED_FILES)


@dataclass
class IndexingJobStatus:
    project_id: str
    status: str = "idle"  # idle | running | completed | completed_with_errors | failed
    files_scanned: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_removed: int = 0
    chunks_created: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None


# Process-local locks and job statuses per project ID
# NOTE: In multi-process deployments, distributed coordination (e.g. Redis locks) would be required.
_PROJECT_LOCKS: Dict[str, asyncio.Lock] = {}
_PROJECT_JOBS: Dict[str, IndexingJobStatus] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def get_project_lock(project_id: str) -> asyncio.Lock:
    async with _REGISTRY_LOCK:
        if project_id not in _PROJECT_LOCKS:
            _PROJECT_LOCKS[project_id] = asyncio.Lock()
        return _PROJECT_LOCKS[project_id]


def get_current_job_status(project_id: str) -> IndexingJobStatus:
    if project_id in _PROJECT_JOBS:
        return _PROJECT_JOBS[project_id]
    return IndexingJobStatus(project_id=project_id, status="idle")


def is_link_or_reparse_point(path: str | Path) -> bool:
    try:
        p_str = str(path)
        if os.path.islink(p_str):
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(p_str):
            return True
        st = os.lstat(p_str)
        if hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT") and bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            return True
    except (OSError, ValueError):
        return True
    return False


def is_indexable_file(file_name: str) -> bool:
    lowered = file_name.lower()
    if lowered in _ALL_IGNORED_FILES:
        return False
    if is_prohibited_file_name(file_name):
        return False
    ext = Path(file_name).suffix.lower()
    return ext in SUPPORTED_EXTENSIONS


def scan_workspace_files(project_root: str | Path) -> Tuple[List[Tuple[str, Path, int]], bool, Optional[str]]:
    """Walk project workspace and discover supported, safe files.

    Returns: (list_of_(relative_path, resolved_path, size), scan_complete_bool, error_message_if_any)
    """
    root = Path(project_root).resolve()
    if not root.is_dir():
        return [], False, "Project root directory not found on disk"

    discovered: List[Tuple[str, Path, int]] = []
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Filter out symlinks/junctions and ignored directories in place
        pruned_dirs = []
        for d in dirnames:
            full_d = os.path.join(dirpath, d)
            if d.lower() in _ALL_IGNORED_DIRS or is_link_or_reparse_point(full_d):
                continue
            pruned_dirs.append(d)
        dirnames[:] = pruned_dirs

        for f in filenames:
            full_f = os.path.join(dirpath, f)
            if is_link_or_reparse_point(full_f):
                continue
            if not is_indexable_file(f):
                continue

            try:
                rel_path = os.path.relpath(full_f, root).replace("\\", "/")
                resolved = resolve_in_project(root, rel_path)
            except Exception:
                continue

            try:
                st = os.stat(resolved)
                file_size = st.st_size
            except OSError:
                continue

            if file_size > MAX_INDEX_FILE_SIZE_BYTES or file_size == 0:
                continue

            discovered.append((rel_path, resolved, file_size))
            total_bytes += file_size

            if len(discovered) >= MAX_INDEX_FILES:
                return discovered, False, f"Scan file count exceeded limit ({MAX_INDEX_FILES})"
            if total_bytes >= MAX_INDEX_TOTAL_BYTES:
                return discovered, False, f"Scan byte volume exceeded limit ({MAX_INDEX_TOTAL_BYTES} bytes)"

    # Stable sorting by relative path
    discovered.sort(key=lambda x: x[0])
    return discovered, True, None


async def index_project_workspace(project: Project, db: AsyncSession) -> IndexingJobStatus:
    """Run persistent AST indexing on a project workspace.

    Guarantees:
    - Atomicity per file.
    - Idempotency when files are unchanged.
    - Stale chunk replacement when modified.
    - Cleanup of stale records only when scan was fully completed.
    - Zero source content or secret leakage in errors.
    """
    lock = await get_project_lock(project.id)
    if lock.locked():
        raise RuntimeError("An indexing job is already in progress for this project.")

    async with lock:
        start_time = time.monotonic()
        started_iso = datetime.now(timezone.utc).isoformat()
        job = IndexingJobStatus(
            project_id=project.id,
            status="running",
            started_at=started_iso,
        )
        _PROJECT_JOBS[project.id] = job

        try:
            candidates, scan_complete, scan_err = scan_workspace_files(project.root_path)
            if scan_err:
                job.errors.append(f"Scan note: {scan_err}")

            job.files_scanned = len(candidates)

            # Query existing ProjectFile records for this project
            res = await db.execute(select(ProjectFile).where(ProjectFile.project_id == project.id))
            existing_files = {pf.file_path: pf for pf in res.scalars().all()}

            processed_rel_paths: Set[str] = set()

            for rel_path, abs_path, file_size in candidates:
                try:
                    # Read bytes
                    try:
                        content_bytes = abs_path.read_bytes()
                    except Exception as exc:
                        job.errors.append(f"Could not read {rel_path}: {exc.__class__.__name__}")
                        continue

                    # Check for binary NUL bytes
                    if b"\x00" in content_bytes:
                        continue

                    current_hash = hashlib.sha256(content_bytes).hexdigest()
                    pf = existing_files.get(rel_path)

                    # Check if unchanged
                    if pf and pf.file_hash == current_hash:
                        chunk_count_res = await db.execute(
                            select(func.count()).select_from(CodeChunk).where(CodeChunk.file_id == pf.id)
                        )
                        chunk_count = chunk_count_res.scalar() or 0
                        if chunk_count > 0:
                            job.files_unchanged += 1
                            processed_rel_paths.add(rel_path)
                            continue

                    # Parse AST with Tree-sitter
                    lang = detect_language(rel_path) or "plaintext"
                    parsed = parse_source(content_bytes, rel_path, language=lang)
                    if not parsed.syntax_valid and parsed.error:
                        job.errors.append(f"Syntax warning in {rel_path}: {parsed.error}")

                    # Decode text into lines
                    text_content = content_bytes.decode("utf-8", errors="replace")
                    lines = split_lines(text_content)
                    total_lines = len(lines)

                    chunks_data = []
                    if parsed.symbols:
                        for sym in parsed.symbols:
                            s_line = max(1, min(sym.start_line, total_lines))
                            e_line = max(s_line, min(sym.end_line, total_lines))
                            chunk_text = "\n".join(lines[s_line - 1 : e_line])
                            chunks_data.append({
                                "chunk_type": sym.kind.value,
                                "symbol_name": sym.name,
                                "start_line": s_line,
                                "end_line": e_line,
                                "content": chunk_text,
                                "metadata_json": {
                                    "parent_symbol": sym.parent_symbol,
                                    "signature": sym.signature,
                                    "docstring": sym.docstring,
                                    "language": parsed.language,
                                },
                            })
                    else:
                        # Module chunk for files with content but no extracted symbols (scripts, imports only)
                        non_empty_lines = [l for l in lines if l.strip()]
                        if non_empty_lines:
                            chunks_data.append({
                                "chunk_type": "module",
                                "symbol_name": None,
                                "start_line": 1,
                                "end_line": total_lines,
                                "content": text_content,
                                "metadata_json": {
                                    "language": parsed.language,
                                    "import_count": len(parsed.imports),
                                    "imports": [imp.module for imp in parsed.imports[:20]],
                                },
                            })

                    # Atomic file update
                    async with db.begin_nested() if db.in_transaction() else db.begin():
                        now_utc = datetime.now(timezone.utc)
                        if not pf:
                            pf = ProjectFile(
                                id=str(uuid.uuid4()),
                                project_id=project.id,
                                file_path=rel_path,
                                file_name=Path(rel_path).name,
                                file_size_bytes=len(content_bytes),
                                language=parsed.language,
                                file_hash=current_hash,
                                last_scanned_at=now_utc,
                            )
                            db.add(pf)
                            await db.flush()
                            existing_files[rel_path] = pf
                        else:
                            pf.file_size_bytes = len(content_bytes)
                            pf.language = parsed.language
                            pf.file_hash = current_hash
                            pf.last_scanned_at = now_utc
                            await db.execute(delete(CodeChunk).where(CodeChunk.file_id == pf.id))
                            await db.flush()

                        for idx, c_info in enumerate(chunks_data):
                            chunk_obj = CodeChunk(
                                id=str(uuid.uuid4()),
                                project_id=project.id,
                                file_id=pf.id,
                                chunk_index=idx,
                                chunk_type=c_info["chunk_type"],
                                symbol_name=c_info["symbol_name"],
                                start_line=c_info["start_line"],
                                end_line=c_info["end_line"],
                                content=c_info["content"],
                                metadata_json=c_info["metadata_json"],
                            )
                            db.add(chunk_obj)
                        await db.flush()

                    await db.commit()
                    job.files_indexed += 1
                    job.chunks_created += len(chunks_data)
                    processed_rel_paths.add(rel_path)

                except Exception as file_exc:
                    await db.rollback()
                    logger.warning("Error indexing file %s: %s", rel_path, file_exc)
                    job.errors.append(f"Failed to index {rel_path}: {file_exc.__class__.__name__}")

            # Stale file cleanup: ONLY when the scan completed cleanly
            if scan_complete:
                for old_path, old_pf in list(existing_files.items()):
                    if old_path not in processed_rel_paths:
                        # File was deleted or is no longer eligible on disk
                        try:
                            async with db.begin_nested() if db.in_transaction() else db.begin():
                                await db.execute(delete(CodeChunk).where(CodeChunk.file_id == old_pf.id))
                                await db.delete(old_pf)
                            await db.commit()
                            job.files_removed += 1
                        except Exception as del_exc:
                            await db.rollback()
                            job.errors.append(f"Failed to remove stale file {old_path}: {del_exc.__class__.__name__}")

            # Completion state
            duration = round(time.monotonic() - start_time, 4)
            job.duration_seconds = duration
            job.completed_at = datetime.now(timezone.utc).isoformat()

            if job.errors:
                job.status = "completed_with_errors"
                # Do not mark is_indexed=True when errors prevented complete indexing
            else:
                job.status = "completed"
                project.is_indexed = True
                project.last_indexed_at = datetime.now(timezone.utc)
                await db.commit()

        except Exception as fatal_exc:
            await db.rollback()
            logger.exception("Fatal error during indexing of project %s", project.id)
            job.status = "failed"
            job.duration_seconds = round(time.monotonic() - start_time, 4)
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.errors.append(f"Fatal indexing failure: {fatal_exc.__class__.__name__}")

        return job
