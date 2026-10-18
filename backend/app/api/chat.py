from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_or_404
from app.database import get_db
from app.models.conversation import Conversation
from app.models.project import Project

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])

CHAT_UNAVAILABLE_DETAIL = (
    "AI chat is not available: no LLM provider integration is implemented or configured yet."
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    mode: Literal["agent", "chat", "review"] = "agent"


class Citation(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    symbol: Optional[str] = None


class PlanStep(BaseModel):
    id: int
    text: str
    tool: str
    status: str = "pending"


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    sender: str
    content: str
    citations: List[Citation]
    plan_steps: List[PlanStep]
    timestamp: str


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_chat_history(project: Project = Depends(get_project_or_404), db: AsyncSession = Depends(get_db)):
    """Return the stored messages of the project's most recent conversation (empty if none)."""
    stmt = (
        select(Conversation)
        .where(Conversation.project_id == project.id)
        .order_by(Conversation.created_at.desc())
    )
    conv = (await db.execute(stmt)).scalars().first()
    if not conv:
        return []

    return [
        {
            "id": m.id,
            "sender": m.sender,
            "content": m.content,
            "citations": m.citations or [],
            "plan_steps": m.plan_steps or [],
            "timestamp": m.created_at.isoformat(),
        }
        for m in conv.messages
    ]


@router.post(
    "",
    response_model=ChatResponse,
    responses={503: {"description": "No AI provider is available"}},
)
async def send_chat_message(payload: ChatRequest, project: Project = Depends(get_project_or_404)):
    """Answer a prompt about the project.

    No model provider is implemented yet, so this reports that honestly (503) instead of
    returning invented text, and stores nothing.
    """
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHAT_UNAVAILABLE_DETAIL)
