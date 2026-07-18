from fastapi import APIRouter, HTTPException

from . import service


router = APIRouter(prefix="/api", tags=["pre-match"])


@router.get("/pre-match-trading-report")
def get_pre_match_trading_report(date: str = "today", limit: int = 12):
    try:
        return service.get_report(date, limit)
    except service.InvalidDate as exc:
        raise HTTPException(400, str(exc)) from exc
