from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import check_database_connection, get_db
from app.api.projects import router as projects_router
from app.api.files import router as files_router
from app.api.chat import router as chat_router

router = APIRouter()

# Include sub-routers
router.include_router(projects_router)
router.include_router(files_router)
router.include_router(chat_router)


@router.get("/health", summary="Basic Liveness Check")
async def health_check():
    """Basic liveness probe."""
    return {
        "status": "healthy",
        "service": "STACKPILOT API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/health", summary="Detailed Readiness Probe")
async def detailed_health():
    """Readiness probe checking database connectivity and environment details."""
    db_status = await check_database_connection()
    return {
        "status": "healthy" if db_status["status"] == "connected" else "degraded",
        "database": db_status["status"],
        "database_type": db_status.get("type", "unknown"),
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/info", summary="System Information")
async def system_info():
    """Return platform metadata, features, and active settings."""
    return {
        "name": "STACKPILOT",
        "tagline": "AI-Powered Software Development Platform",
        "version": "0.1.0",
        "status": "operational",
        "capabilities": [
            "Codebase Indexing (AST)",
            "Semantic RAG Retrieval",
            "Agent Planning & Tool Calling",
            "Multi-File Modification & Diff Review",
            "Sandboxed Execution & Testing",
            "Automated Debugging Loops",
            "Git Integration",
        ],
        "active_providers": {
            "llm": settings.LLM_PROVIDER,
            "embedding": settings.EMBEDDING_PROVIDER,
        }
    }
