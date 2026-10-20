"""Read-only compatibility projection for the retired trade_records table."""
from __future__ import annotations

from xiaoxue_api.modules.market_notes.public import list_notes


class InvalidLegacyTrade(ValueError):
    pass


class LegacyTradeNotFound(LookupError):
    pass


class LegacyTradesUnavailable(RuntimeError):
    pass


def _record(note: dict) -> dict:
    return {
        "id": note.get("id", ""), "game": "lol", "match_name": note.get("match_name", ""),
        "match_time": note.get("match_time", ""), "pick_winner": "", "pick_total": "",
        "score_pick": note.get("score_note", ""), "reason": note.get("reason", ""),
        "confidence": note.get("confidence", ""), "result": "未结算", "review": note.get("review", ""),
        "linked_team": note.get("linked_team", ""), "created_at": note.get("created_at", ""),
        "updated_at": note.get("updated_at", ""), "source": "trading_tk",
    }


def list_trades(game: str = "", result: str = "", limit: int = 30) -> dict:
    try:
        notes = list_notes(game, limit).get("records") or []
    except (OSError, ValueError, RuntimeError) as exc:
        raise LegacyTradesUnavailable("交易 TK 正源暂时不可用") from exc
    records = [_record(note) for note in notes]
    if result:
        records = [record for record in records if record["result"] == result]
    return {"records": records, "source": "trading_tk", "deprecated": True}


def trade_stats(game: str = "") -> dict:
    records = list_trades(game, "", 200).get("records") or []
    return {"total": len(records), "settled": 0, "wins": 0, "losses": 0, "pushes": 0, "win_rate": 0, "by_game": {}}
