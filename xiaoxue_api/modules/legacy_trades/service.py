from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import repository


CONFIG_PATH = Path(__file__).with_name("config.json")
UPDATE_FIELDS = (
    "game", "match_name", "match_time", "pick_winner", "pick_total",
    "score_pick", "reason", "confidence", "result", "review", "linked_team",
)
GAME_ALIASES = {
    "英雄联盟": "lol", "联盟": "lol", "无畏": "valorant",
    "无畏契约": "valorant", "瓦": "valorant", "足球": "football",
}


class InvalidLegacyTrade(ValueError):
    pass


class LegacyTradeNotFound(LookupError):
    pass


class LegacyTradesUnavailable(RuntimeError):
    pass


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LegacyTradesUnavailable(f"旧交易兼容配置不可用：{exc}") from exc


def normalize_game(value: str) -> str:
    game = (value or "lol").strip().lower()
    game = GAME_ALIASES.get(game, game)
    games = set(load_config().get("games") or ["lol"])
    return game if game in games else "lol"


def row_payload(row) -> dict:
    return {
        "id": row["id"], "game": row["game"], "match_name": row["match_name"],
        "match_time": row["match_time"] or "", "pick_winner": row["pick_winner"] or "放弃",
        "pick_total": row["pick_total"] or "放弃", "score_pick": row["score_pick"] or "",
        "reason": row["reason"] or "", "confidence": row["confidence"] or "中",
        "result": row["result"] or "未结算", "review": row["review"] or "",
        "linked_team": row["linked_team"] or "", "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_trades(game: str = "", result: str = "", limit: int = 30) -> dict:
    try:
        rows = repository.list_rows(normalize_game(game) if game else "", result, limit)
    except sqlite3.Error as exc:
        raise LegacyTradesUnavailable("旧交易记录暂时不可用") from exc
    return {"records": [row_payload(row) for row in rows]}


def create_trade(values: dict) -> dict:
    payload = dict(values)
    payload["match_name"] = (payload.get("match_name") or "").strip()
    if not payload["match_name"]:
        raise InvalidLegacyTrade("比赛不能为空")
    payload["game"] = normalize_game(payload.get("game") or "lol")
    results = set(load_config().get("results") or ["未结算"])
    if payload.get("result") not in results:
        payload["result"] = "未结算"
    try:
        row = repository.create(payload)
    except sqlite3.Error as exc:
        raise LegacyTradesUnavailable("旧交易记录暂时不可用") from exc
    return {"ok": True, "record": row_payload(row)}


def update_trade(trade_id: int, values: dict) -> dict:
    payload = {key: values[key] for key in UPDATE_FIELDS if key in values}
    if not payload:
        raise InvalidLegacyTrade("没有可更新字段")
    if "game" in payload:
        payload["game"] = normalize_game(payload["game"])
    if "result" in payload:
        results = set(load_config().get("results") or ["未结算"])
        if payload["result"] not in results:
            payload["result"] = "未结算"
    try:
        row = repository.update(trade_id, payload)
    except sqlite3.Error as exc:
        raise LegacyTradesUnavailable("旧交易记录暂时不可用") from exc
    if not row:
        raise LegacyTradeNotFound("记录不存在")
    return {"ok": True, "record": row_payload(row)}


def delete_trade(trade_id: int) -> dict:
    try:
        deleted = repository.delete(trade_id)
    except sqlite3.Error as exc:
        raise LegacyTradesUnavailable("旧交易记录暂时不可用") from exc
    if not deleted:
        raise LegacyTradeNotFound("记录不存在")
    return {"ok": True}


def trade_stats(game: str = "") -> dict:
    try:
        rows = repository.stats_rows(normalize_game(game) if game else "")
    except sqlite3.Error as exc:
        raise LegacyTradesUnavailable("旧交易记录暂时不可用") from exc
    settled = [row for row in rows if row["result"] in ("赢", "输", "走水")]
    wins = sum(1 for row in rows if row["result"] == "赢")
    losses = sum(1 for row in rows if row["result"] == "输")
    pushes = sum(1 for row in rows if row["result"] == "走水")
    by_game: dict[str, dict] = {}
    for row in rows:
        bucket = by_game.setdefault(
            row["game"], {"total": 0, "wins": 0, "losses": 0, "pushes": 0}
        )
        bucket["total"] += 1
        if row["result"] == "赢":
            bucket["wins"] += 1
        if row["result"] == "输":
            bucket["losses"] += 1
        if row["result"] == "走水":
            bucket["pushes"] += 1
    return {
        "total": len(rows), "settled": len(settled), "wins": wins,
        "losses": losses, "pushes": pushes,
        "win_rate": round(wins / len(settled) * 100, 1) if settled else 0,
        "by_game": by_game,
    }
