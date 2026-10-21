import logging
import uuid
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_or_404
from app.database import get_db
from app.models.conversation import Conversation, Message
from app.models.project import Project
from app.services.grounding import answer_grounded, CITATION_INVALID
from app.services.llm import provider_status

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])

# aiosqlite logs every SQL statement WITH its parameters at DEBUG, and DEBUG is the development default. That would print
# each stored question and answer (which may contain code) to the server log, so this one library stays at INFO.
logging.getLogger("aiosqlite").setLevel(logging.INFO)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    mode: Literal["agent", "chat", "review"] = "agent"


class Citation(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    symbol: Optional[str] = None
    # Set for grounded answers (Stage 3c): verified | stale. Citations that are invalid are not listed here.
    status: Optional[str] = None
    excerpt_id: Optional[str] = None
    file_sha256: Optional[str] = None
    range_sha256: Optional[str] = None


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
    plan_steps: List[PlanStep]  # always empty: this chat is read-only and proposes no steps
    timestamp: str
    # answered_verified | answered_unverified | not_in_context | unavailable
    status: str
    # retrieval counts and citation metadata (including invalid citations); never source text
    grounding: Optional[Dict[str, Any]] = None


class ChatStatus(BaseModel):
    provider: str
    model: Optional[str] = None
    configured: bool
    consent: bool
    can_send: bool
    reason: Optional[str] = None


@router.get("/status", response_model=ChatStatus)
async def get_chat_status(project: Project = Depends(get_project_or_404)):
    """Whether a question can be sent to an AI provider right now, and if not, why. Never contains a key."""
    return provider_status()


LEGACY = "legacy"


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_chat_history(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Return the stored messages of the project's most recent conversation.

    `status` is the stored grounded-answer status; an assistant message written before answers were grounded has none
    and is reported as "legacy" (never as verified). User messages have no status.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.project_id == project.id)
        .order_by(Conversation.created_at.desc())
    )
    conv = (await db.execute(stmt)).scalars().first()
    if not conv:
        return []

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    messages = (await db.execute(msg_stmt)).scalars().all()
    if not messages:
        return []

    return [
        {
            "id": m.id,
            "sender": m.sender,
            "content": m.content,
            "citations": m.citations or [],
            "plan_steps": m.plan_steps or [],
            "timestamp": m.created_at.isoformat(),
            "status": m.status if m.status else (LEGACY if m.sender == "assistant" else None),
            "grounding": m.grounding,
        }
        for m in messages
    ]


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_history(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Clear chat conversations for the project."""
    stmt = select(Conversation).where(Conversation.project_id == project.id)
    convs = (await db.execute(stmt)).scalars().all()
    for c in convs:
        await db.delete(c)
    await db.commit()
    return None


@router.post("", response_model=ChatResponse)
async def send_chat_message(
    payload: ChatRequest,
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
):
    """Answer a question about the project from its own files, with citations that have been checked.

    Every question stands alone: no earlier message is sent anywhere. Configuration and consent are checked before any
    file is read (see app/services/grounding.py).
    """
    # A conversation id must belong to THIS project; otherwise nothing happens (no fallback to another conversation).
    conv = None
    if payload.conversation_id:
        conv = (
            (
                await db.execute(
                    select(Conversation).where(Conversation.id == payload.conversation_id, Conversation.project_id == project.id)
                )
            )
            .scalars()
            .first()
        )
        if conv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found in this project.")
    else:
        stmt = (
            select(Conversation)
            .where(Conversation.project_id == project.id)
            .order_by(Conversation.created_at.desc())
        )
        conv = (await db.execute(stmt)).scalars().first()

    # No database write is pending while the provider is being waited for.
    answer = await answer_grounded(payload.message, project.root_path)

    if conv is None:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project.id, title="Engineering Session")
        db.add(conv)
        await db.flush()

    # Verified and stale citations are listed; invalid ones appear only (as metadata, without model-supplied text) in `grounding`.
    citations = [
        Citation(
            file_path=c.path,
            line_start=c.start_line,
            line_end=c.end_line,
            status=c.status,
            excerpt_id=c.excerpt_id,
            file_sha256=c.file_sha256,
            range_sha256=c.range_sha256,
        )
        for c in answer.citations
        if c.status != CITATION_INVALID
    ]
    grounding = dict(answer.grounding)

    asst_msg_id = str(uuid.uuid4())
    db.add(Message(id=str(uuid.uuid4()), conversation_id=conv.id, sender="user", content=payload.message, citations=[], plan_steps=[]))
    db.add(
        Message(
            id=asst_msg_id,
            conversation_id=conv.id,
            sender="assistant",
            content=answer.content,
            citations=[c.model_dump() for c in citations],
            plan_steps=[],
            status=answer.status,
            grounding=grounding,
        )
    )
    await db.commit()

    return ChatResponse(
        conversation_id=conv.id,
        message_id=asst_msg_id,
        sender="assistant",
        content=answer.content,
        citations=citations,
        plan_steps=[],
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=answer.status,
        grounding=grounding,
    )
