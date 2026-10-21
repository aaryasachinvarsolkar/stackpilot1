from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from app.config import settings
from app.api.routes import router as api_router
from app.api.run import ProxyPreflightMiddleware
from app.services import runner
from app.database import engine
from app.database.migrations import ensure_database_ready

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stackpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown routines."""
    logger.info("Initializing STACKPILOT Backend Service...")
    # Never migrates an existing database implicitly: creates the schema only on an empty
    # database, otherwise verifies the revision and refuses to start if it is not current.
    reaped = await asyncio.to_thread(runner.reap_orphans)  # project servers left over from a hard stop of an earlier backend
    if reaped:
        logger.warning("Stopped %d project server(s) left running by an earlier backend.", len(reaped))
    await ensure_database_ready(engine)
    logger.info(f"Database ready. Environment: {settings.ENVIRONMENT}")
    yield
    logger.info("Shutting down STACKPILOT Backend Service...")
    await runner.stop_all()  # never leave a project's process running after the backend is gone
    await engine.dispose()


app = FastAPI(
    title="STACKPILOT API",
    description="AI-Powered Software Development Platform Backend API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

UPLOAD_PATH = "/api/projects/upload"
_MULTIPART_OVERHEAD = 1024 * 1024  # form fields and boundaries around the ZIP itself


class UploadSizeLimitMiddleware:
    """Refuse an oversized ZIP upload while its body is still arriving.

    Starlette spools a multipart body to a temporary file before any endpoint code runs, so the endpoint's own limit
    could not stop a huge upload from filling the disk. This looks at the declared length first and then counts the bytes
    that really arrive. The endpoint still enforces the exact limit on the ZIP itself.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return
        limit = settings.MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD
        message = f"The upload is larger than the {settings.MAX_UPLOAD_BYTES} byte limit."
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": message}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=message)
            return event

        await self.app(scope, limited_receive, send)


# Middleware order: the one added last is outermost. The Host check must run before everything else (CORS, routing, any
# endpoint), and CORS must wrap the size guard so a 413 still carries CORS headers the browser can read.
app.add_middleware(UploadSizeLimitMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The project proxy answers its own CORS preflights (the sandboxed page is not one of this app's trusted origins). Only that path.
app.add_middleware(ProxyPreflightMiddleware)

# Host header allowlist (loopback names only): answers 400 before any endpoint runs. Guards against DNS rebinding.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# Register routes
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
