from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import LineupWorkflowIn
from .service import ConfigurationUnavailable, prepare


router = APIRouter(prefix="/api", tags=["lineup"])


@router.post("/lineup-workflow/prepare")
def prepare_lineup(data: LineupWorkflowIn):
    try:
        return prepare(data.model_dump())
    except ConfigurationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
