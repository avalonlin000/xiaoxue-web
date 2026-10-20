"""Deprecated compatibility projection for the retired market-notes tables.

Trading judgments now have one durable source: category=market entries in the
existing trading TK library.  This module intentionally exposes only a read
projection for old clients; it never creates database tables or writes records.
"""
from __future__ import annotations

from xiaoxue_api.modules.tk_knowledge.public import list_general_trading_tk


class MarketNotesUnavailable(RuntimeError):
    pass


def _record(item: dict) -> dict:
    """Map the trading-TK contract to the legacy read shape without copying it."""
    statement = str(item.get("statement") or "").strip()
    subject = str(item.get("subject") or "").strip()
    return {
        "id": str(item.get("filename") or ""),
        "game": "lol",
        "match_name": statement,
        "match_time": "",
        "direction": "",
        "total_lean": "TK",
        "score_note": "",
        "reason": str(item.get("context") or ""),
        "confidence": "",
        "review": str(item.get("review_note") or ""),
        "linked_team": subject,
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "filename": str(item.get("filename") or ""),
        "source": "trading_tk",
    }


def list_notes(game: str = "", limit: int = 30) -> dict:
    if game and game.strip().lower() != "lol":
        return {"records": [], "source": "trading_tk", "deprecated": True}
    try:
        payload = list_general_trading_tk(status="all", limit=max(1, min(int(limit or 30), 200)), game="lol")
    except (OSError, ValueError, RuntimeError) as exc:
        raise MarketNotesUnavailable("交易 TK 正源暂时不可用") from exc
    records = [_record(item) for item in payload.get("items") or []]
    return {
        "records": records,
        "source": "trading_tk",
        "deprecated": True,
        "successor": "/api/trading-tk",
    }
