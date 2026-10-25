from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS basket_items (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            module_id TEXT NOT NULL,
            module_name TEXT NOT NULL,
            optional_note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            is_focus INTEGER NOT NULL DEFAULT 0,
            context_snapshot TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            archived_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_basket_items_status ON basket_items(status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS change_requests (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            module_id TEXT NOT NULL,
            module_name TEXT NOT NULL,
            basket_item_ids TEXT NOT NULL,
            user_problem TEXT NOT NULL,
            desired_experience TEXT NOT NULL,
            desired_result TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            triage_summary TEXT NOT NULL DEFAULT '',
            impact_summary TEXT NOT NULL DEFAULT '',
            locked_decisions TEXT NOT NULL DEFAULT '',
            delivery_summary TEXT NOT NULL DEFAULT '',
            verification_summary TEXT NOT NULL DEFAULT '',
            user_validation_path TEXT NOT NULL DEFAULT '',
            blockers TEXT NOT NULL DEFAULT '',
            archived_reason TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            archived_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_change_requests_status ON change_requests(status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS deliveries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            request_id TEXT,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            user_visible_change TEXT NOT NULL,
            verification_evidence TEXT NOT NULL DEFAULT '[]',
            known_risks TEXT NOT NULL DEFAULT '',
            user_validation_path TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            feedback_action TEXT NOT NULL DEFAULT '',
            feedback_note TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            archived_at TEXT,
            FOREIGN KEY(request_id) REFERENCES change_requests(id)
        );
        CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS lifecycle_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            owner TEXT NOT NULL,
            event_type TEXT NOT NULL,
            before_snapshot TEXT NOT NULL DEFAULT '{}',
            after_snapshot TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_lifecycle_entity ON lifecycle_events(entity_type, entity_id, occurred_at DESC);
        CREATE TABLE IF NOT EXISTS idempotency_records (
            operation TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(operation, idempotency_key)
        );
        """
    )


def fetch_one(connection: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = connection.execute(query, params).fetchone()
    return _row(row) if row else None


def fetch_all(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [_row(row) for row in connection.execute(query, params).fetchall()]


def insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )


def update(connection: sqlite3.Connection, table: str, entity_id: str, revision: int, values: dict[str, Any]) -> bool:
    assignments = ", ".join(f"{column}=?" for column in values)
    cursor = connection.execute(
        f"UPDATE {table} SET {assignments}, revision=revision+1 WHERE id=? AND revision=?",
        (*values.values(), entity_id, revision),
    )
    return cursor.rowcount == 1


def record_event(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    occurred_at: str,
    owner: str,
    event_type: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO lifecycle_events
           (entity_type, entity_id, occurred_at, owner, event_type, before_snapshot, after_snapshot)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_type,
            entity_id,
            occurred_at,
            owner,
            event_type,
            json.dumps(before or {}, ensure_ascii=False, separators=(",", ":")),
            json.dumps(after or {}, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def idempotency_record(connection: sqlite3.Connection, operation: str, key: str) -> dict[str, Any] | None:
    return fetch_one(
        connection,
        "SELECT * FROM idempotency_records WHERE operation=? AND idempotency_key=?",
        (operation, key),
    )


def save_idempotency(
    connection: sqlite3.Connection,
    *,
    operation: str,
    key: str,
    entity_type: str,
    entity_id: str,
    payload_hash: str,
    created_at: str,
) -> None:
    insert(connection, "idempotency_records", {
        "operation": operation,
        "idempotency_key": key,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload_hash": payload_hash,
        "created_at": created_at,
    })


def _row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key in ("context_snapshot", "basket_item_ids", "verification_evidence", "before_snapshot", "after_snapshot"):
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                result[key] = [] if key in {"basket_item_ids", "verification_evidence"} else {}
    if "is_focus" in result:
        result["is_focus"] = bool(result["is_focus"])
    return result
