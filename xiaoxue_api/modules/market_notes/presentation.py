from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from . import service


router = APIRouter(prefix="/api/market-notes", tags=["deprecated-market-notes"])
SUNSET_MESSAGE = "盘口记录表已退役；盘口判断唯一正源为交易 TK，请使用 /api/trading-tk。"


def _deprecated_headers() -> dict[str, str]:
    return {"Deprecation": "true", "Link": "</api/trading-tk>; rel=successor-version"}


@router.get("")
def list_notes(response: Response, game: str = Query(""), limit: int = Query(30, ge=1, le=200)):
    try:
        response.headers.update(_deprecated_headers())
        return service.list_notes(game, limit)
    except service.MarketNotesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("", include_in_schema=False)
@router.delete("/{note_id}", include_in_schema=False)
@router.post("/{note_id}/review-preview", include_in_schema=False)
@router.put("/{note_id}/review", include_in_schema=False)
def retired_write(note_id: str = ""):
    raise HTTPException(410, SUNSET_MESSAGE, headers=_deprecated_headers())
