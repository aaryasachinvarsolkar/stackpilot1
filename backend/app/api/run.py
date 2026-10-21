"""Run the whole project: start/stop its backend, and let the sandboxed page talk to it.

The page itself is shown by api/preview.py in a sandboxed iframe (opaque origin). Its calls to its own backend go through
`/api/projects/{id}/app/...` here: a plain forwarder to the one port this app started for that project on 127.0.0.1. It
never forwards anywhere else. See services/runner.py for what running means and how it is fenced in.
"""
import asyncio
import re
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.preview import project_by_id
from app.models.project import Project
from app.services import runner

router = APIRouter(prefix="/api/projects/{project_id}", tags=["run"])

_STATUS = {"not_allowed": 403, "no_plan": 422, "bad_plan": 422, "too_many_runs": 409, "tool_missing": 422}
MAX_BODY_BYTES = 10 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 60.0

# The page runs in an opaque origin, so every answer it reads needs these. The sandbox is repeated on every proxied answer in
# case the project's backend serves HTML itself.
_OPEN_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Expose-Headers": "*",
    "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups",
    "Referrer-Policy": "no-referrer",
}
_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "content-length", "content-encoding", "host"}
_NOT_FORWARDED = _HOP_BY_HOP | {"origin", "referer", "cookie", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"}
_APP_PATH = re.compile(r"^/api/projects/[^/]+/app(/|$)")


def _fail(err: runner.RunError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(err.code, 400), detail={"code": err.code, "message": err.message})


@router.get("/run")
async def run_status(project: Project = Depends(project_by_id)):
    """What can be run, whether it is allowed, and what it is doing now (with the latest log lines)."""
    return runner.status(project.id, project.root_path)


@router.post("/run/start", status_code=202)
async def run_start(project: Project = Depends(project_by_id)):
    """Install (first time only) and start the project's backend in the background. Needs ALLOW_RUNNING_PROJECT_CODE=true."""
    try:
        runner.start_run(project.id, project.root_path)
    except runner.RunError as err:
        raise _fail(err)
    return runner.status(project.id, project.root_path)


@router.post("/run/restart", status_code=202)
async def run_restart(project: Project = Depends(project_by_id)):
    """Stop and start again (the dependency install is skipped when nothing changed)."""
    try:
        await runner.restart_run(project.id, project.root_path)
    except runner.RunError as err:
        raise _fail(err)
    return runner.status(project.id, project.root_path)


@router.post("/run/stop")
async def run_stop(project: Project = Depends(project_by_id)):
    await runner.stop_run(project.id)
    return runner.status(project.id, project.root_path)


# --- the forwarder -----------------------------------------------------------------------------------------------------
class ProxyPreflightMiddleware:
    """Answer CORS preflights for the project proxy only.

    The app-wide CORS layer (which only trusts this app's own pages) would reject a preflight from the sandboxed page. It is
    NOT widened: this handles just `/api/projects/<id>/app/...`, and every other path goes through untouched.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and scope["method"] == "OPTIONS" and _APP_PATH.match(scope["path"]):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if "access-control-request-method" in headers:
                response = Response(
                    status_code=204,
                    headers={
                        **_OPEN_HEADERS,
                        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
                        "Access-Control-Allow-Headers": headers.get("access-control-request-headers", "*"),
                        "Access-Control-Max-Age": "600",
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


@router.api_route("/app/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
async def proxy_http(path: str, request: Request, project_id: str):
    run = runner.active_run(project_id)
    if run is None:
        return Response(
            '{"detail":"This project is not running. Start it from the Run tab."}', status_code=409, media_type="application/json", headers=_OPEN_HEADERS,
        )
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response('{"detail":"Request body too large."}', status_code=413, media_type="application/json", headers=_OPEN_HEADERS)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _NOT_FORWARDED}
    url = f"http://127.0.0.1:{run.port}/{path}"  # the host and port are never taken from the request
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS, follow_redirects=False) as client:
            upstream = await client.request(request.method, url, params=request.query_params.multi_items(), content=body, headers=headers)
    except httpx.HTTPError:
        return Response('{"detail":"The project did not answer. Check its log in the Run tab."}', status_code=502, media_type="application/json", headers=_OPEN_HEADERS)
    out = {k: v for k, v in upstream.headers.multi_items() if k.lower() not in _HOP_BY_HOP and not k.lower().startswith("access-control-") and k.lower() not in ("content-security-policy", "set-cookie")}
    out.update(_OPEN_HEADERS)
    return Response(upstream.content, status_code=upstream.status_code, headers=out)


@router.websocket("/app/{path:path}")
async def proxy_websocket(websocket: WebSocket, project_id: str, path: str):
    from websockets.asyncio.client import connect

    run = runner.active_run(project_id)
    if run is None:
        await websocket.close(code=1013)
        return
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    query = websocket.url.query
    uri = f"ws://127.0.0.1:{run.port}/{path}" + (f"?{query}" if query else "")
    try:
        upstream = await connect(uri, max_size=4 * 1024 * 1024, open_timeout=10, subprotocols=offered or None)  # type: ignore[arg-type]
    except Exception:
        await websocket.close(code=1011)
        return
    await websocket.accept(subprotocol=upstream.subprotocol)

    async def to_project():
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") is not None:
                await upstream.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream.send(message["bytes"])

    async def to_page():
        async for message in upstream:
            if isinstance(message, str):
                await websocket.send_text(message)
            else:
                await websocket.send_bytes(message)

    tasks = [asyncio.create_task(to_project()), asyncio.create_task(to_page())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await upstream.close()
        try:
            await websocket.close()
        except Exception:
            pass
