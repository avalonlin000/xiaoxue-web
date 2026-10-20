from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from . import service


router = APIRouter(prefix="/api/trades", tags=["legacy-trades"])
SUNSET_MESSAGE = "旧交易记录接口已退役；请使用 /api/trading-tk 保存和读取交易 TK。"


def _deprecated_headers() -> dict[str, str]:
    return {"Deprecation": "true", "Link": "</api/trading-tk>; rel=successor-version"}


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


@router.get("", deprecated=True)
def list_trades(
    response: Response, game: str = Query(""), result: str = Query(""), limit: int = Query(30)
):
    response.headers.update(_deprecated_headers())
    return _present(service.list_trades, game, result, limit)


@router.post("", include_in_schema=False)
def create_trade(data: TradeRecordIn):
    raise HTTPException(410, SUNSET_MESSAGE, headers=_deprecated_headers())


@router.get("/stats", deprecated=True)
def trade_stats(response: Response, game: str = Query("")):
    response.headers.update(_deprecated_headers())
    return _present(service.trade_stats, game)


@router.put("/{trade_id}", include_in_schema=False)
def update_trade(trade_id: int, data: TradeRecordUpdate):
    raise HTTPException(410, SUNSET_MESSAGE, headers=_deprecated_headers())


@router.delete("/{trade_id}", include_in_schema=False)
def delete_trade(trade_id: int):
    raise HTTPException(410, SUNSET_MESSAGE, headers=_deprecated_headers())


def _present(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except service.InvalidLegacyTrade as exc:
        raise HTTPException(400, str(exc)) from exc
    except service.LegacyTradeNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.LegacyTradesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
