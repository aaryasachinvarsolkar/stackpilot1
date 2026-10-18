from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router as api_router
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
    await ensure_database_ready(engine)
    logger.info(f"Database ready. Environment: {settings.ENVIRONMENT}")
    yield
    logger.info("Shutting down STACKPILOT Backend Service...")
    await engine.dispose()


app = FastAPI(
    title="STACKPILOT API",
    description="AI-Powered Software Development Platform Backend API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
