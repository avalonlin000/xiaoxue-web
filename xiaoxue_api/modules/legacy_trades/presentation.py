from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import service


router = APIRouter(prefix="/api/trades", tags=["legacy-trades"])


class TradeRecordIn(BaseModel):
    game: str = "lol"
    match_name: str
    match_time: str = ""
    pick_winner: str = "放弃"
    pick_total: str = "放弃"
    score_pick: str = ""
    reason: str = ""
    confidence: str = "中"
    result: str = "未结算"
    review: str = ""
    linked_team: str = ""


class TradeRecordUpdate(BaseModel):
    game: str | None = None
    match_name: str | None = None
    match_time: str | None = None
    pick_winner: str | None = None
    pick_total: str | None = None
    score_pick: str | None = None
    reason: str | None = None
    confidence: str | None = None
    result: str | None = None
    review: str | None = None
    linked_team: str | None = None


@router.get("")
def list_trades(
    game: str = Query(""), result: str = Query(""), limit: int = Query(30)
):
    return _present(service.list_trades, game, result, limit)


@router.post("")
def create_trade(data: TradeRecordIn):
    return _present(service.create_trade, data.model_dump())


@router.get("/stats")
def trade_stats(game: str = Query("")):
    return _present(service.trade_stats, game)


@router.put("/{trade_id}")
def update_trade(trade_id: int, data: TradeRecordUpdate):
    return _present(service.update_trade, trade_id, data.model_dump(exclude_unset=True))


@router.delete("/{trade_id}")
def delete_trade(trade_id: int):
    return _present(service.delete_trade, trade_id)


def _present(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except service.InvalidLegacyTrade as exc:
        raise HTTPException(400, str(exc)) from exc
    except service.LegacyTradeNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.LegacyTradesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
