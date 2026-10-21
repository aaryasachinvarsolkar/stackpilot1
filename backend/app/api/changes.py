from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_project_or_404
from app.models.project import Project
from app.services import changes

router = APIRouter(prefix="/api/projects/{project_id}/changes", tags=["changes"])

_STATUS = {
    "not_sendable": 503, "provider_error": 502, "malformed_reply": 502, "retrieval_failed": 500,
    "proposal_not_found": 404, "project_missing": 404,
    "file_changed": 409, "already_done": 409, "not_applied": 409, "apply_failed": 409, "revert_failed": 409,
    "no_usable_edits": 422, "no_usable_steps": 422,
}


async def _run(coro):
    try:
        return await coro
    except changes.ChangeError as err:
        raise HTTPException(status_code=_STATUS.get(err.code, 400), detail={"code": err.code, "message": err.message})


class AnalyzeRequest(BaseModel):
    request: str = Field(..., max_length=changes.MAX_REQUEST_CHARS)


class PlanStep(BaseModel):
    action: str  # "modify" (an existing file) or "create" (a new one)
    path: str
    what: str = Field("", max_length=400)


class ProposeRequest(BaseModel):
    request: str = Field(..., max_length=changes.MAX_REQUEST_CHARS)
    notes: Optional[str] = Field(None, max_length=changes.MAX_REQUEST_CHARS)
    steps: List[PlanStep] = Field(..., max_length=changes.MAX_STEPS)  # the steps of the plan the user approved


class ApplyRequest(BaseModel):
    proposal_id: str
    paths: List[str]  # only these are written; the rest of the proposal is left alone


class RevertRequest(BaseModel):
    proposal_id: str


@router.post("/analyze")
async def analyze_change(payload: AnalyzeRequest, project: Project = Depends(get_project_or_404)):
    """Read-only: which files a described change affects, how risky it is, and what to decide first."""
    return await _run(changes.analyze(payload.request, project.root_path))


@router.post("/propose")
async def propose_change(payload: ProposeRequest, project: Project = Depends(get_project_or_404)):
    """Build exact edits (with diffs) for the chosen files. Nothing is written."""
    return await _run(changes.propose(project.id, project.root_path, payload.request, payload.notes or "", [step.model_dump() for step in payload.steps]))


@router.post("/apply")
async def apply_change(payload: ApplyRequest, project: Project = Depends(get_project_or_404)):
    """Write the approved files of a proposal, only if none of them changed since it was made."""
    return await _run(changes.apply(project.id, project.root_path, payload.proposal_id, payload.paths))


@router.post("/revert")
async def revert_change(payload: RevertRequest, project: Project = Depends(get_project_or_404)):
    """Restore the originals of an applied change, only if the files still hold what was written."""
    return await _run(changes.revert(project.id, project.root_path, payload.proposal_id))
