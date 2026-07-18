from __future__ import annotations

from datetime import datetime

from xiaoxue_api.core.database import connect


TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS trade_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT NOT NULL DEFAULT 'lol',
        match_name TEXT NOT NULL,
        match_time TEXT DEFAULT '',
        pick_winner TEXT DEFAULT '放弃',
        pick_total TEXT DEFAULT '放弃',
        score_pick TEXT DEFAULT '',
        reason TEXT DEFAULT '',
        confidence TEXT DEFAULT '中',
        result TEXT DEFAULT '未结算',
        review TEXT DEFAULT '',
        linked_team TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""


def ensure_table() -> None:
    """Create the compatibility table only when a legacy operation is requested."""
    conn = connect()
    try:
        conn.execute(TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_records_game_time "
            "ON trade_records(game, match_time, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trade_records_result ON trade_records(result)"
        )
        conn.commit()
    finally:
        conn.close()


def list_rows(game: str, result: str, limit: int):
    ensure_table()
    wheres: list[str] = []
    params: list[object] = []
    if game:
        wheres.append("game = ?")
        params.append(game)
    if result:
        wheres.append("result = ?")
        params.append(result)
    where_clause = "WHERE " + " AND ".join(wheres) if wheres else ""
    conn = connect()
    try:
        return conn.execute(
            f"""SELECT * FROM trade_records
                {where_clause}
                ORDER BY COALESCE(NULLIF(match_time, ''), created_at) DESC, id DESC
                LIMIT ?""",
            params + [limit],
        ).fetchall()
    finally:
        conn.close()


def create(values: dict):
    ensure_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    try:
        cursor = conn.execute(
            """INSERT INTO trade_records
               (game, match_name, match_time, pick_winner, pick_total, score_pick,
                reason, confidence, result, review, linked_team, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["game"], values["match_name"], values.get("match_time", ""),
                values.get("pick_winner", "放弃"), values.get("pick_total", "放弃"),
                values.get("score_pick", ""), values.get("reason", ""),
                values.get("confidence", "中"), values.get("result", "未结算"),
                values.get("review", ""), values.get("linked_team", ""), now, now,
            ),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM trade_records WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    finally:
        conn.close()


def update(trade_id: int, values: dict):
    ensure_table()
    conn = connect()
    try:
        if not conn.execute(
            "SELECT id FROM trade_records WHERE id=?", (trade_id,)
        ).fetchone():
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = list(values.items())
        set_clause = ", ".join(f"{key}=?" for key, _ in updates) + ", updated_at=?"
        conn.execute(
            f"UPDATE trade_records SET {set_clause} WHERE id=?",
            [value for _, value in updates] + [now, trade_id],
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM trade_records WHERE id=?", (trade_id,)
        ).fetchone()
    finally:
        conn.close()


def delete(trade_id: int) -> bool:
    ensure_table()
    conn = connect()
    try:
        cursor = conn.execute("DELETE FROM trade_records WHERE id=?", (trade_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def stats_rows(game: str):
    ensure_table()
    conn = connect()
    try:
        if game:
            return conn.execute(
                "SELECT game, result, pick_winner, pick_total FROM trade_records WHERE game=?",
                (game,),
            ).fetchall()
        return conn.execute(
            "SELECT game, result, pick_winner, pick_total FROM trade_records"
        ).fetchall()
    finally:
        conn.close()
