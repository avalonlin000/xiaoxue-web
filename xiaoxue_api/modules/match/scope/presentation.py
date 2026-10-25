from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import service


router = APIRouter(prefix="/api/lol-scope", tags=["lol-scope"])


@router.get("/overview")
def scope_overview():
    try:
        return service.get_scope_overview()
    except service.ScopeUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/coverage")
def coverage(date: str = Query("today"), days: int = Query(1, ge=1, le=30)):
    try:
        return service.get_coverage(date, days)
    except service.ScopeUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
