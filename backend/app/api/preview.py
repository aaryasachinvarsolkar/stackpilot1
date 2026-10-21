from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.services import preview, runner

router = APIRouter(prefix="/api/projects/{project_id}", tags=["preview"])

# The served page runs in an opaque origin (sandbox without allow-same-origin), so its scripts cannot call this API,
# read its storage or touch other projects. CORS is opened for GET only because a page in an opaque origin must be
# allowed to load its own module scripts and fetch its own files; the project is addressed by its unguessable id.
PREVIEW_HEADERS = {
    "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Access-Control-Allow-Origin": "*",
}


async def project_by_id(project_id: str, db: AsyncSession = Depends(get_db)) -> Project:
    """Exact id only: unlike the rest of the API a preview address never resolves a project by its (guessable) name."""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.get("/preview-info")
async def preview_info(project: Project = Depends(project_by_id)):
    """How this project can be shown in the browser: a static page, a project that needs a server, or nothing."""
    return preview.describe_project(project.root_path)


_REWRITABLE = ("text/html", "text/javascript", "text/css", "application/json")
MAX_REWRITE_BYTES = 5 * 1024 * 1024


@router.get("/preview/{path:path}")
async def preview_file(path: str, request: Request, project: Project = Depends(project_by_id)):
    """One file of the project, read from disk now, for the sandboxed live preview.

    While the project's backend is running, text files have the project's own `http://localhost:<port>` (and ws://) addresses
    pointed at this app's forwarder for the project (see api/run.py), because the real port is chosen at start. Only the copy
    that is sent changes; the file on disk is never touched. The number of replacements is reported in `X-StackPilot-Rewrites`.
    """
    try:
        full = preview.resolve_served_file(project.root_path, path)
    except preview.PreviewPathError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err), headers=PREVIEW_HEADERS)
    media_type = preview.content_type_for(full.name)
    run = runner.active_run(project.id)
    if run is not None and run.plan.app_ports and media_type.startswith(_REWRITABLE) and full.stat().st_size <= MAX_REWRITE_BYTES:
        text = full.read_bytes().decode("utf-8", errors="replace")
        rewritten, count = runner.rewrite_origins(text, run.plan.app_ports, f"{request.url.scheme}://{request.headers.get('host', '127.0.0.1')}", project.id)
        if count:
            return Response(rewritten, media_type=media_type, headers={**PREVIEW_HEADERS, "X-StackPilot-Rewrites": str(count)})
    return FileResponse(full, media_type=media_type, headers=PREVIEW_HEADERS)
