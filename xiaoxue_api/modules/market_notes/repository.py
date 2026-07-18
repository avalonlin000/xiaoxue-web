from __future__ import annotations

from datetime import datetime

from xiaoxue_api.core.database import connect


def ensure_table() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL DEFAULT 'lol',
                match_name TEXT NOT NULL,
                match_time TEXT DEFAULT '',
                direction TEXT DEFAULT '',
                total_lean TEXT DEFAULT '放弃',
                score_note TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                confidence TEXT DEFAULT '中',
                review TEXT DEFAULT '',
                linked_team TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_notes_game_time ON market_notes(game, match_time, created_at)"
        )


def get(note_id: int):
    ensure_table()
    with connect() as conn:
        return conn.execute("SELECT * FROM market_notes WHERE id=?", (note_id,)).fetchone()


def list_rows(game: str, limit: int):
    ensure_table()
    with connect() as conn:
        if game:
            return conn.execute(
                """SELECT * FROM market_notes WHERE game=?
                   ORDER BY COALESCE(NULLIF(match_time, ''), created_at) DESC, id DESC LIMIT ?""",
                (game, limit),
            ).fetchall()
        return conn.execute(
            """SELECT * FROM market_notes
               ORDER BY COALESCE(NULLIF(match_time, ''), created_at) DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def create(values: dict):
    ensure_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO market_notes
               (game, match_name, match_time, direction, total_lean, score_note, reason,
                confidence, review, linked_team, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["game"], values["match_name"], values.get("match_time", ""),
                values.get("direction", ""), values.get("total_lean", "放弃"),
                values.get("score_note", ""), values.get("reason", ""),
                values.get("confidence", "中"), values.get("review", ""),
                values.get("linked_team", ""), now, now,
            ),
        )
        return conn.execute("SELECT * FROM market_notes WHERE id=?", (cursor.lastrowid,)).fetchone()


def update_review(note_id: int, review_text: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        conn.execute(
            "UPDATE market_notes SET review=?, updated_at=? WHERE id=?",
            (review_text, now, note_id),
        )
        return conn.execute("SELECT * FROM market_notes WHERE id=?", (note_id,)).fetchone()


def delete(note_id: int) -> bool:
    ensure_table()
    with connect() as conn:
        cursor = conn.execute("DELETE FROM market_notes WHERE id=?", (note_id,))
        return cursor.rowcount > 0
