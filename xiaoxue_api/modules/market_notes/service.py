from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from workflow_contracts import build_market_note_review

from . import repository


CONFIG_PATH = Path(__file__).with_name("config.json")


class InvalidMarketNote(ValueError):
    pass


class MarketNoteNotFound(LookupError):
    pass


class MarketNotesUnavailable(RuntimeError):
    pass


def row_payload(row) -> dict:
    return {
        "id": row["id"], "game": row["game"], "match_name": row["match_name"],
        "match_time": row["match_time"] or "", "direction": row["direction"] or "",
        "total_lean": row["total_lean"] or "放弃", "score_note": row["score_note"] or "",
        "reason": row["reason"] or "", "confidence": row["confidence"] or "中",
        "review": row["review"] or "", "linked_team": row["linked_team"] or "",
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def normalize_game(value: str) -> str:
    config = load_config()
    games = set((config.get("market") or {}).get("games") or ["lol"])
    game = (value or "lol").strip().lower()
    return game if game in games else "lol"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MarketNotesUnavailable(f"盘口记录模块配置不可用：{exc}") from exc


def get_note(note_id: int) -> dict:
    try:
        row = repository.get(note_id)
    except sqlite3.Error as exc:
        raise MarketNotesUnavailable("盘口记录数据暂时不可用") from exc
    if not row:
        raise MarketNoteNotFound("记录不存在")
    return row_payload(row)


def list_notes(game: str = "", limit: int = 30) -> dict:
    try:
        rows = repository.list_rows(normalize_game(game) if game else "", limit)
    except sqlite3.Error as exc:
        raise MarketNotesUnavailable("盘口记录数据暂时不可用") from exc
    return {"records": [row_payload(row) for row in rows]}


def create_note(values: dict) -> dict:
    values = dict(values)
    values["match_name"] = (values.get("match_name") or "").strip()
    if not values["match_name"]:
        raise InvalidMarketNote("对象不能为空")
    values["game"] = normalize_game(values.get("game") or "lol")
    try:
        row = repository.create(values)
    except sqlite3.Error as exc:
        raise MarketNotesUnavailable("盘口记录数据暂时不可用") from exc
    return {"ok": True, "record": row_payload(row)}


def delete_note(note_id: int) -> bool:
    try:
        return repository.delete(note_id)
    except sqlite3.Error as exc:
        raise MarketNotesUnavailable("盘口记录数据暂时不可用") from exc


def review(note_id: int, payload: dict, *, commit: bool) -> dict:
    if commit and not payload.get("confirmed"):
        raise InvalidMarketNote("必须明确确认后才能写入复盘")
    try:
        result = build_market_note_review(get_note(note_id), payload, load_config())
    except ValueError as exc:
        raise InvalidMarketNote(str(exc)) from exc
    if not commit:
        return result
    try:
        row = repository.update_review(note_id, result["review_text"])
    except sqlite3.Error as exc:
        raise MarketNotesUnavailable("盘口记录数据暂时不可用") from exc
    return {"ok": True, "record": row_payload(row), **result}
