from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .models import TradingNoteIn, TradingNoteTextIn
from . import service


router = APIRouter(prefix="/api", tags=["tk-knowledge"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, service.ModuleUnavailable):
        raise HTTPException(503, str(exc)) from exc
    if isinstance(exc, service.TeamUnconfirmed):
        raise HTTPException(422, str(exc)) from exc
    if isinstance(exc, service.EntryNotFound):
        raise HTTPException(404, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


@router.get("/tk/search")
def search_tk(q: str = Query(...), team: str = Query(None), limit: int = Query(20)):
    return service.search(q, team, limit)


@router.get("/tk/library")
def browse_tk_library(
    period: str = Query("all"), month: str = Query(""), q: str = Query(""),
    team: str = Query(""), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
):
    try:
        return service.browse(period, month, q, team, offset, limit)
    except service.InvalidInput as exc:
        _raise_http(exc)


@router.get("/tk/entry/{filename}")
def get_tk_library_entry(filename: str):
    try:
        return service.get_entry(filename)
    except (service.InvalidInput, service.EntryNotFound, service.ModuleUnavailable) as exc:
        _raise_http(exc)


@router.get("/version-understanding/{team}")
def get_version_understanding(team: str, limit: int = Query(8)):
    try:
        return service.get_version_understanding(team, limit)
    except service.InvalidInput as exc:
        _raise_http(exc)


@router.post("/tk")
def create_tk(data: dict):
    try:
        return service.create(data)
    except service.InvalidInput as exc:
        _raise_http(exc)


@router.post("/team-trading-notes")
def create_team_trading_note(data: TradingNoteIn):
    try:
        return service.create_team_trading_note(data)
    except (service.InvalidInput, service.EntryNotFound, service.ModuleUnavailable) as exc:
        _raise_http(exc)


@router.post("/team-trading-notes/from-text")
def create_team_trading_note_from_text(data: TradingNoteTextIn):
    try:
        return service.create_team_trading_note(service.parse_trading_note_text(data.text))
    except (service.InvalidInput, service.EntryNotFound, service.TeamUnconfirmed, service.ModuleUnavailable) as exc:
        _raise_http(exc)


@router.get("/team-trading-notes/{team}")
def list_team_trading_notes(team: str, status: str = "active", limit: int = 20):
    try:
        return service.list_team_trading_notes(team, status, limit)
    except (service.InvalidInput, service.EntryNotFound, service.ModuleUnavailable) as exc:
        _raise_http(exc)


@router.put("/tk/{filename}")
def update_tk(filename: str, data: dict):
    try:
        return service.update(filename, data)
    except (service.InvalidInput, service.EntryNotFound) as exc:
        _raise_http(exc)


@router.delete("/tk/{filename}")
def delete_tk(filename: str):
    try:
        return service.delete(filename)
    except (service.InvalidInput, service.EntryNotFound) as exc:
        _raise_http(exc)
