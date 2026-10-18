import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.config import settings

logger = logging.getLogger(__name__)

# Determine connect_args based on DB dialect (e.g. check_same_thread for SQLite)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def check_database_connection() -> dict:
    """Check connectivity to the configured database and return status."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_type = "sqlite" if "sqlite" in settings.DATABASE_URL else "postgresql"
        return {
            "status": "connected",
            "type": db_type,
            "error": None
        }
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return {
            "status": "error",
            "type": "unknown",
            "error": str(e)
        }
