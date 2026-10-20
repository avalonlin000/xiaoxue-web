from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone


def initialize(connection: sqlite3.Connection) -> None:
    """Create the isolated research-core schema on a caller-owned connection."""
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS research_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(domain, subject_key)
        );

        CREATE TABLE IF NOT EXISTS research_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES research_subjects(id)
        );

        CREATE TABLE IF NOT EXISTS research_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            event_id INTEGER,
            kind TEXT NOT NULL,
            source_name TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES research_subjects(id),
            FOREIGN KEY(event_id) REFERENCES research_events(id)
        );

        CREATE TABLE IF NOT EXISTS research_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            event_id INTEGER,
            kind TEXT NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES research_subjects(id),
            FOREIGN KEY(event_id) REFERENCES research_events(id)
        );

        CREATE TABLE IF NOT EXISTS research_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            event_id INTEGER,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            source_material_ids TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES research_subjects(id),
            FOREIGN KEY(event_id) REFERENCES research_events(id)
        );

        CREATE TABLE IF NOT EXISTS research_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            event_id INTEGER,
            outcome TEXT NOT NULL,
            review TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES research_subjects(id),
            FOREIGN KEY(event_id) REFERENCES research_events(id)
        );

        CREATE INDEX IF NOT EXISTS idx_research_events_subject
            ON research_events(subject_id, occurred_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_research_materials_subject
            ON research_materials(subject_id, captured_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_research_notes_subject
            ON research_notes(subject_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_research_digests_subject
            ON research_digests(subject_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_research_reviews_subject
            ON research_reviews(subject_id, created_at DESC, id DESC);
        """
    )


def open_subject(connection: sqlite3.Connection, *, domain: str, subject_key: str, name: str) -> dict:
    now = _now()
    connection.execute(
        """
        INSERT INTO research_subjects (domain, subject_key, name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(domain, subject_key) DO UPDATE SET
            name=excluded.name,
            updated_at=excluded.updated_at
        """,
        (domain, subject_key, name, now, now),
    )
    return _row(
        connection.execute(
            "SELECT * FROM research_subjects WHERE domain=? AND subject_key=?",
            (domain, subject_key),
        ).fetchone()
    )


def add_event(
    connection: sqlite3.Connection,
    *,
    subject_id: int,
    kind: str,
    title: str,
    occurred_at: str,
    details: str,
) -> dict:
    cursor = connection.execute(
        """
        INSERT INTO research_events (subject_id, kind, title, occurred_at, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (subject_id, kind, title, occurred_at, details, _now()),
    )
    return _row(connection.execute("SELECT * FROM research_events WHERE id=?", (cursor.lastrowid,)).fetchone())


def add_material(
    connection: sqlite3.Connection,
    *,
    subject_id: int,
    event_id: int | None,
    kind: str,
    source_name: str,
    source_url: str,
    content: str,
    captured_at: str,
) -> dict:
    cursor = connection.execute(
        """
        INSERT INTO research_materials (
            subject_id, event_id, kind, source_name, source_url, content, captured_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (subject_id, event_id, kind, source_name, source_url, content, captured_at, _now()),
    )
    return _row(connection.execute("SELECT * FROM research_materials WHERE id=?", (cursor.lastrowid,)).fetchone())


def add_note(
    connection: sqlite3.Connection,
    *,
    subject_id: int,
    event_id: int | None,
    kind: str,
    author: str,
    content: str,
) -> dict:
    cursor = connection.execute(
        """
        INSERT INTO research_notes (subject_id, event_id, kind, author, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (subject_id, event_id, kind, author, content, _now()),
    )
    return _row(connection.execute("SELECT * FROM research_notes WHERE id=?", (cursor.lastrowid,)).fetchone())


def add_digest(connection: sqlite3.Connection, *, subject_id: int, event_id: int | None, kind: str, content: str, source_material_ids: list[int]) -> dict:
    cursor = connection.execute(
        """INSERT INTO research_digests (subject_id, event_id, kind, content, source_material_ids, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (subject_id, event_id, kind, content, json.dumps(source_material_ids), _now()),
    )
    return _digest_row(connection.execute("SELECT * FROM research_digests WHERE id=?", (cursor.lastrowid,)).fetchone())


def add_review(connection: sqlite3.Connection, *, subject_id: int, event_id: int | None, outcome: str, review: str) -> dict:
    cursor = connection.execute("INSERT INTO research_reviews (subject_id, event_id, outcome, review, created_at) VALUES (?, ?, ?, ?, ?)", (subject_id, event_id, outcome, review, _now()))
    return _row(connection.execute("SELECT * FROM research_reviews WHERE id=?", (cursor.lastrowid,)).fetchone())


def get_subject(connection: sqlite3.Connection, subject_id: int) -> dict | None:
    row = connection.execute("SELECT * FROM research_subjects WHERE id=?", (subject_id,)).fetchone()
    return _row(row) if row else None


def list_subjects(connection: sqlite3.Connection, *, query: str = "", limit: int = 20) -> list[dict]:
    clean_query = query.strip()
    params: list[object] = []
    where = ""
    if clean_query:
        where = "WHERE domain LIKE ? OR subject_key LIKE ? OR name LIKE ?"
        token = f"%{clean_query}%"
        params.extend((token, token, token))
    params.append(limit)
    return _rows(connection.execute(
        f"SELECT * FROM research_subjects {where} ORDER BY updated_at DESC, id DESC LIMIT ?", params
    ).fetchall())


def get_event(connection: sqlite3.Connection, event_id: int) -> dict | None:
    row = connection.execute("SELECT * FROM research_events WHERE id=?", (event_id,)).fetchone()
    return _row(row) if row else None


def get_material(connection: sqlite3.Connection, material_id: int) -> dict | None:
    row = connection.execute("SELECT * FROM research_materials WHERE id=?", (material_id,)).fetchone()
    return _row(row) if row else None


def list_events(connection: sqlite3.Connection, subject_id: int) -> list[dict]:
    return _rows(connection.execute(
        "SELECT * FROM research_events WHERE subject_id=? ORDER BY occurred_at DESC, id DESC", (subject_id,)
    ).fetchall())


def list_materials(connection: sqlite3.Connection, subject_id: int) -> list[dict]:
    return _rows(connection.execute(
        "SELECT * FROM research_materials WHERE subject_id=? ORDER BY captured_at DESC, id DESC", (subject_id,)
    ).fetchall())


def list_notes(connection: sqlite3.Connection, subject_id: int) -> list[dict]:
    return _rows(connection.execute(
        "SELECT * FROM research_notes WHERE subject_id=? ORDER BY created_at DESC, id DESC", (subject_id,)
    ).fetchall())


def list_digests(connection: sqlite3.Connection, subject_id: int) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM research_digests WHERE subject_id=? ORDER BY created_at DESC, id DESC", (subject_id,)
    ).fetchall()
    return [_digest_row(row) for row in rows]


def list_reviews(connection: sqlite3.Connection, subject_id: int) -> list[dict]:
    return _rows(connection.execute("SELECT * FROM research_reviews WHERE subject_id=? ORDER BY created_at DESC, id DESC", (subject_id,)).fetchall())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def _rows(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _digest_row(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["source_material_ids"] = json.loads(result["source_material_ids"])
    return result
