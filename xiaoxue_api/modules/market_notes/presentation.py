from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import service


router = APIRouter(prefix="/api/market-notes", tags=["market-notes"])


class MarketNoteIn(BaseModel):
    game: str = "lol"
    match_name: str
    match_time: str = ""
    direction: str = ""
    total_lean: str = "放弃"
    score_note: str = ""
    reason: str = ""
    confidence: str = "中"
    review: str = ""
    linked_team: str = ""


class MarketReviewIn(BaseModel):
    result: str = "未结算"
    actual_score: str = ""
    actual_lineup: str = ""
    key_turns: str = ""
    correct_points: str = ""
    wrong_points: str = ""
    missing_evidence: str = ""
    calibration: str = ""
    destinations: list[str] = Field(default_factory=lambda: ["market_notes"])
    confirmed: bool = False


@router.post("/{note_id}/review-preview")
def preview_review(note_id: int, data: MarketReviewIn):
    return _present(service.review, note_id, data.model_dump(), commit=False)


@router.put("/{note_id}/review")
def commit_review(note_id: int, data: MarketReviewIn):
    return _present(service.review, note_id, data.model_dump(), commit=True)


@router.get("")
def list_notes(game: str = Query(""), limit: int = Query(30)):
    return _present(service.list_notes, game, limit)


@router.post("")
def create_note(data: MarketNoteIn):
    return _present(service.create_note, data.model_dump())


@router.delete("/{note_id}")
def delete_note(note_id: int):
    if not _present(service.delete_note, note_id):
        raise HTTPException(404, "记录不存在")
    return {"ok": True}


def _present(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except service.InvalidMarketNote as exc:
        raise HTTPException(400, str(exc)) from exc
    except service.MarketNoteNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.MarketNotesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
