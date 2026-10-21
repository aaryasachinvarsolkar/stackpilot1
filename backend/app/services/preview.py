"""Live preview: find out how a project can run in the browser, and serve its files safely.

What is supported, and what deliberately is not
  static   the project has an HTML page (index.html). Its files are served read-only and shown in a sandboxed iframe, so
           the page, its scripts and styles run in the browser. Nothing on the server executes: no project code, no
           install step, no shell. The files are read from disk on every request, so a saved or applied change shows up
           on the next load.
  server   the project needs a program running behind it (Flask, FastAPI, Express, Next, Vite, ...). This module only
           DETECTS and explains that. Starting it is a separate, owner-switched feature (services/runner.py, behind
           ALLOW_RUNNING_PROJECT_CODE): this module and api/preview.py never start a process.

Safety of what is served (see api/preview.py for the headers)
  * only files inside the project, by the same path rules as the file API; dot-files and dot-folders, dependency and
    version-control folders, and secret-like names (.env, keys, secrets*, credentials*) are never served;
  * the response carries `Content-Security-Policy: sandbox ...` WITHOUT allow-same-origin, so the page runs in an opaque
    origin: its JavaScript cannot call this API (CORS blocks it), read its cookies or storage, or touch other projects.
"""
from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.indexer import is_prohibited_file_name
from app.services.workspace import UnsafePathError, resolve_in_project

MAX_SERVED_BYTES = 25 * 1024 * 1024
MAX_WALK_ENTRIES = 6000
MAX_DEPTH = 5
MAX_CANDIDATES = 8

# Never served and never searched. Unlike the editor's list this one allows `dist` and `build`: a built site is a fine preview.
BLOCKED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".idea", ".vscode", ".next", ".svn", ".hg"})
PREFERRED_DIRS = ("", "public", "frontend", "client", "web", "www", "site", "static", "docs", "app", "src", "dist", "build")

_FRAMEWORK_DEPS = {
    "next": "Next.js", "react-scripts": "Create React App", "vite": "Vite", "@angular/core": "Angular", "vue": "Vue",
    "nuxt": "Nuxt", "svelte": "Svelte", "express": "Express", "koa": "Koa", "fastify": "Fastify", "@nestjs/core": "NestJS",
    "gatsby": "Gatsby", "astro": "Astro", "remix": "Remix",
}
_PY_SERVER_WORDS = (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"), ("streamlit", "Streamlit"), ("uvicorn", "uvicorn"), ("tornado", "Tornado"), ("aiohttp", "aiohttp"))

_MIME_OVERRIDES = {
    ".js": "text/javascript", ".mjs": "text/javascript", ".cjs": "text/javascript", ".css": "text/css", ".json": "application/json",
    ".map": "application/json", ".svg": "image/svg+xml", ".wasm": "application/wasm", ".webmanifest": "application/manifest+json",
    ".html": "text/html", ".htm": "text/html", ".txt": "text/plain", ".md": "text/plain", ".ico": "image/x-icon", ".woff2": "font/woff2",
    ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf", ".webp": "image/webp", ".avif": "image/avif",
}


def _blocked_part(part: str) -> bool:
    return part.startswith(".") or part.lower() in BLOCKED_DIRS


def content_type_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    kind = _MIME_OVERRIDES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    return f"{kind}; charset=utf-8" if kind.startswith("text/") or kind in ("application/json", "image/svg+xml") else kind


class PreviewPathError(Exception):
    """The requested file is not something the preview serves. The message is safe to show."""


def resolve_served_file(project_root: str, relative: str) -> Path:
    """Map a URL path to a real file inside the project, or raise PreviewPathError. A folder maps to its index.html."""
    cleaned = (relative or "").replace("\\", "/").strip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if any(_blocked_part(p) for p in parts) or any(p == ".." for p in parts):
        raise PreviewPathError("Not available.")
    try:
        root = Path(project_root).resolve()
        full = resolve_in_project(root, "/".join(parts)) if parts else root
    except (UnsafePathError, OSError, ValueError):
        raise PreviewPathError("Not available.") from None
    if full.is_dir():
        full = full / "index.html"
    if not full.is_file() or full.is_symlink() or is_prohibited_file_name(full.name) or full.name.startswith("."):
        raise PreviewPathError("Not available.")
    try:
        if full.stat().st_size > MAX_SERVED_BYTES:
            raise PreviewPathError("That file is too large to preview.")
    except OSError:
        raise PreviewPathError("Not available.") from None
    return full


def _rank(rel_dir: str, depth: int) -> tuple:
    top = rel_dir.split("/")[0] if rel_dir else ""
    return (depth, PREFERRED_DIRS.index(top) if top in PREFERRED_DIRS else len(PREFERRED_DIRS), rel_dir)


def _read_small(path: Path, limit: int = 200_000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def describe_project(project_root: str) -> Dict[str, Any]:
    """How this project can be run in the browser. Reads names and a few small manifest files; executes nothing."""
    root = Path(project_root)
    if not root.is_dir():
        return {"kind": "none", "entry": None, "candidates": [], "hints": [], "needs_backend": False, "message": "The project's folder does not exist on disk."}

    pages: List[tuple] = []  # (rank, path)
    hints: List[str] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        depth = 0 if not rel_dir else rel_dir.count("/") + 1
        dirnames[:] = sorted(d for d in dirnames if not _blocked_part(d) and not os.path.islink(os.path.join(dirpath, d)))
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        for name in sorted(filenames):
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                dirnames[:] = []
                break
            rel = f"{rel_dir}/{name}" if rel_dir else name
            lowered = name.lower()
            if lowered == "index.html" and not is_prohibited_file_name(name):
                pages.append((_rank(rel_dir, depth), rel))
            elif lowered == "package.json" and depth <= 2:
                text = _read_small(Path(dirpath, name))
                for dep, label in _FRAMEWORK_DEPS.items():
                    if re.search(rf'"{re.escape(dep)}"\s*:', text):
                        hints.append(f"{label} app ({rel}): needs its dev server")
                        break
                else:
                    if re.search(r'"(dev|start)"\s*:', text):
                        hints.append(f"Node project ({rel}): has a start script")
            elif lowered in ("requirements.txt", "pyproject.toml", "pipfile") and depth <= 2:
                text = _read_small(Path(dirpath, name)).lower()
                for word, label in _PY_SERVER_WORDS:
                    if word in text:
                        hints.append(f"{label} backend ({rel}): needs a Python server")
                        break
            elif lowered == "manage.py" and depth <= 2:
                hints.append(f"Django project ({rel}): needs a Python server")

    pages.sort()
    candidates = [{"path": p} for _rank_key, p in pages[:MAX_CANDIDATES]]
    hints = list(dict.fromkeys(hints))[:6]
    if candidates:
        return {
            "kind": "static", "entry": candidates[0]["path"], "candidates": candidates, "hints": hints, "needs_backend": bool(hints),
            "message": (
                "This page runs in the browser from your files. It also looks like it has a server part: start the backend below, "
                "otherwise anything that loads data from that server will not work." if hints else "This page runs in the browser from your files."
            ),
        }
    if hints:
        return {
            "kind": "server", "entry": None, "candidates": [], "hints": hints, "needs_backend": True,
            "message": (
                "This project needs a running server (and probably an install step). Start it with the button below. That runs the "
                "project's own code on your computer, so it only works when the owner has allowed it in the backend settings."
            ),
        }
    return {"kind": "none", "entry": None, "candidates": [], "hints": [], "needs_backend": False, "message": "No web page (index.html) was found in this project, so there is nothing to show in the browser."}
