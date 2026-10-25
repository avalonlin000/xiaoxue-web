from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from xiaoxue_api.core.database import db
from xiaoxue_api.core.project_identity import load_project_identity

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_event_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    template = config.pop("plan_path_template", "")
    if template:
        config["plan_path"] = load_project_identity().resolve_path_template(template)
    return config


def read_plan(path: str) -> dict | None:
    target = Path(path)
    if not target.is_file():
        return None
    return {
        "content": target.read_text(encoding="utf-8"),
        "updated_at": datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


def ensure_workspace_tables() -> None:
    """Create the additive match-workspace storage without touching older records."""
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_key TEXT NOT NULL UNIQUE,
                game TEXT NOT NULL DEFAULT 'lol',
                team_a TEXT NOT NULL,
                team_b TEXT NOT NULL,
                event TEXT NOT NULL DEFAULT '',
                match_date TEXT NOT NULL,
                match_time TEXT NOT NULL DEFAULT '',
                match_format TEXT NOT NULL DEFAULT '',
                current_direction TEXT NOT NULL,
                current_reasons TEXT NOT NULL,
                current_handling TEXT NOT NULL,
                change_conditions TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                trade_plan_manual TEXT NOT NULL DEFAULT '{}',
                trade_plan_frozen TEXT NOT NULL DEFAULT '{}',
                trade_plan_state TEXT NOT NULL DEFAULT 'draft'
            )
        """)
        _ensure_column(conn, "match_workspaces", "trade_plan_manual", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "match_workspaces", "trade_plan_frozen", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "match_workspaces", "trade_plan_state", "TEXT NOT NULL DEFAULT 'draft'")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_workspaces_date
            ON match_workspaces(game, match_date, updated_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                impact TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(workspace_id) REFERENCES match_workspaces(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_observations_workspace
            ON match_observations(workspace_id, id DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_trade_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_key TEXT NOT NULL UNIQUE,
                game TEXT NOT NULL DEFAULT 'lol',
                team_a TEXT NOT NULL,
                team_b TEXT NOT NULL,
                match_date TEXT NOT NULL,
                match_time TEXT NOT NULL DEFAULT '',
                auto_plan TEXT NOT NULL DEFAULT '{}',
                manual_plan TEXT NOT NULL DEFAULT '{}',
                frozen_plan TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_trade_plans_date ON match_trade_plans(game, match_date, updated_at DESC)")


def get_trade_plan(match_key: str):
    with db() as conn:
        if not _table_exists(conn, "match_trade_plans"):
            return None
        return conn.execute("SELECT * FROM match_trade_plans WHERE match_key=?", (match_key,)).fetchone()


def upsert_trade_plan(values: dict):
    ensure_workspace_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("""
            INSERT INTO match_trade_plans (
                match_key, game, team_a, team_b, match_date, match_time,
                auto_plan, manual_plan, frozen_plan, state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                auto_plan=excluded.auto_plan, manual_plan=excluded.manual_plan,
                frozen_plan=excluded.frozen_plan, state=excluded.state, updated_at=excluded.updated_at
        """, (
            values["match_key"], values["game"], values["team_a"], values["team_b"], values["match_date"], values["match_time"],
            json.dumps(values.get("auto_plan") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(values.get("manual_plan") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(values.get("frozen_plan") or {}, ensure_ascii=False, sort_keys=True),
            values.get("state") or "draft", now, now,
        ))
        return conn.execute("SELECT * FROM match_trade_plans WHERE match_key=?", (values["match_key"],)).fetchone()


def get_workspace(match_key: str):
    with db() as conn:
        if not _table_exists(conn, "match_workspaces"):
            return None
        return conn.execute("SELECT * FROM match_workspaces WHERE match_key=?", (match_key,)).fetchone()


def upsert_workspace(values: dict):
    ensure_workspace_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("""
            INSERT INTO match_workspaces (
                match_key, game, team_a, team_b, event, match_date, match_time, match_format,
                current_direction, current_reasons, current_handling, change_conditions,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                current_direction=excluded.current_direction,
                current_reasons=excluded.current_reasons,
                current_handling=excluded.current_handling,
                change_conditions=excluded.change_conditions,
                updated_at=excluded.updated_at
        """, (
            values["match_key"], values["game"], values["team_a"], values["team_b"], values["event"],
            values["match_date"], values["match_time"], values["match_format"], values["direction"],
            values["reasons"], values["handling"], values["change_conditions"], now, now,
        ))
        return conn.execute("SELECT * FROM match_workspaces WHERE match_key=?", (values["match_key"],)).fetchone()


def list_observations(workspace_id: int, limit: int = 12):
    with db() as conn:
        if not _table_exists(conn, "match_observations"):
            return []
        return conn.execute("""
            SELECT * FROM match_observations WHERE workspace_id=?
            ORDER BY id DESC LIMIT ?
        """, (workspace_id, limit)).fetchall()


def create_observation(workspace_id: int, values: dict):
    ensure_workspace_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        cursor = conn.execute("""
            INSERT INTO match_observations (workspace_id, source, impact, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (workspace_id, values["source"], values["impact"], values["detail"], now))
        return conn.execute("SELECT * FROM match_observations WHERE id=?", (cursor.lastrowid,)).fetchone()


def ensure_match_run_tables() -> None:
    """Create additive temporary trade-thread records without changing old workspaces."""
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_key TEXT NOT NULL UNIQUE,
                game TEXT NOT NULL DEFAULT 'lol',
                team_a TEXT NOT NULL,
                team_b TEXT NOT NULL,
                event TEXT NOT NULL DEFAULT '',
                match_date TEXT NOT NULL,
                match_time TEXT NOT NULL DEFAULT '',
                match_format TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'virtual_pre',
                phase TEXT NOT NULL DEFAULT 'fact_check',
                cutoff_at TEXT NOT NULL DEFAULT '',
                result_unlocked INTEGER NOT NULL DEFAULT 0,
                virtual_direction TEXT NOT NULL DEFAULT '',
                virtual_reasons TEXT NOT NULL DEFAULT '',
                virtual_handling TEXT NOT NULL DEFAULT '',
                virtual_change_conditions TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        _ensure_column(conn, "match_runs", "activity_status", "TEXT NOT NULL DEFAULT 'paused'")
        _ensure_column(conn, "match_runs", "current_focus", "TEXT NOT NULL DEFAULT 'overview'")
        _ensure_column(conn, "match_runs", "last_opened_at", "TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_run_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                fact_code TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                source_ref TEXT NOT NULL DEFAULT '',
                as_of TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                affects TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(run_id, fact_code),
                FOREIGN KEY(run_id) REFERENCES match_runs(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_run_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                fact_id INTEGER NOT NULL,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL DEFAULT '',
                old_value TEXT NOT NULL DEFAULT '',
                new_value TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES match_runs(id),
                FOREIGN KEY(fact_id) REFERENCES match_run_facts(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_run_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                section TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(run_id, section),
                FOREIGN KEY(run_id) REFERENCES match_runs(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_update_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_name TEXT NOT NULL,
                topic TEXT NOT NULL,
                observation TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES match_runs(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_runs_date ON match_runs(game, match_date, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_runs_activity ON match_runs(activity_status, last_opened_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_run_facts_run ON match_run_facts(run_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_run_revisions_run ON match_run_revisions(run_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_run_entries_run ON match_run_entries(run_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_status ON knowledge_update_candidates(status, updated_at DESC)")
        conn.execute("""
            UPDATE match_runs SET current_focus='version'
            WHERE current_focus='trend'
              AND NOT EXISTS (
                  SELECT 1 FROM match_run_entries
                  WHERE match_run_entries.run_id=match_runs.id AND match_run_entries.section='trend'
              )
        """)


def _ensure_column(conn, table: str, column: str, declaration: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _table_exists(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def get_match_run(match_key: str):
    with db() as conn:
        if not _table_exists(conn, "match_runs"):
            return None
        return conn.execute("SELECT * FROM match_runs WHERE match_key=?", (match_key,)).fetchone()


def get_match_run_by_identity(values: dict):
    """Find one run even if a schedule later spells the event name differently."""
    with db() as conn:
        if not _table_exists(conn, "match_runs"):
            return None
        return conn.execute("""
            SELECT * FROM match_runs
            WHERE game=? AND team_a=? AND team_b=? AND match_date=? AND match_time=?
            ORDER BY updated_at DESC, id DESC LIMIT 1
        """, (
            values["game"], values["team_a"], values["team_b"], values["match_date"], values["match_time"],
        )).fetchone()


def create_match_run(values: dict):
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("""
            INSERT INTO match_runs (
                match_key, game, team_a, team_b, event, match_date, match_time, match_format,
                mode, phase, cutoff_at, result_unlocked, activity_status, current_focus,
                last_opened_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'fact_check', ?, 0, 'paused', ?, ?, ?, ?)
            ON CONFLICT(match_key) DO NOTHING
        """, (
            values["match_key"], values["game"], values["team_a"], values["team_b"], values["event"],
            values["match_date"], values["match_time"], values["match_format"], values["mode"],
            values["cutoff_at"], values.get("focus") or "overview", now, now, now,
        ))
        return conn.execute("SELECT * FROM match_runs WHERE match_key=?", (values["match_key"],)).fetchone()


def activate_match_run(run_id: int, *, focus: str | None = None, mode: str | None = None):
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("UPDATE match_runs SET activity_status='paused' WHERE activity_status='active' AND id<>?", (run_id,))
        assignments = ["activity_status='active'", "last_opened_at=?", "updated_at=?"]
        params: list[object] = [now, now]
        if focus is not None:
            assignments.append("current_focus=?")
            params.append(focus)
        if mode is not None:
            assignments.append("mode=?")
            params.append(mode)
        params.append(run_id)
        conn.execute(f"UPDATE match_runs SET {', '.join(assignments)} WHERE id=?", params)
        return conn.execute("SELECT * FROM match_runs WHERE id=?", (run_id,)).fetchone()


def pause_match_run(run_id: int):
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("UPDATE match_runs SET activity_status='paused', updated_at=? WHERE id=?", (now, run_id))
        return conn.execute("SELECT * FROM match_runs WHERE id=?", (run_id,)).fetchone()


def get_active_match_run():
    with db() as conn:
        if not _table_exists(conn, "match_runs"):
            return None
        return conn.execute("""
            SELECT * FROM match_runs WHERE activity_status='active'
            ORDER BY last_opened_at DESC, id DESC LIMIT 1
        """).fetchone()


def list_recent_match_runs(limit: int = 12):
    with db() as conn:
        if not _table_exists(conn, "match_runs"):
            return []
        return conn.execute("""
            SELECT * FROM match_runs
            ORDER BY CASE activity_status WHEN 'active' THEN 0 ELSE 1 END,
                     last_opened_at DESC, updated_at DESC, id DESC LIMIT ?
        """, (limit,)).fetchall()


def list_match_run_entries(run_id: int):
    with db() as conn:
        if not _table_exists(conn, "match_run_entries"):
            return []
        return conn.execute("""
            SELECT * FROM match_run_entries WHERE run_id=? ORDER BY id
        """, (run_id,)).fetchall()


def upsert_match_run_entry(run_id: int, section: str, content: str):
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        conn.execute("""
            INSERT INTO match_run_entries (run_id, section, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id, section) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
        """, (run_id, section, content, now, now))
        conn.execute("""
            UPDATE match_runs SET current_focus=?, activity_status='active', last_opened_at=?, updated_at=? WHERE id=?
        """, (section, now, now, run_id))
        return conn.execute("SELECT * FROM match_run_entries WHERE run_id=? AND section=?", (run_id, section)).fetchone()


def list_match_run_facts(run_id: int):
    with db() as conn:
        if not _table_exists(conn, "match_run_facts"):
            return []
        return conn.execute("SELECT * FROM match_run_facts WHERE run_id=? ORDER BY id", (run_id,)).fetchall()


def create_match_run_facts(run_id: int, facts: list[dict]) -> None:
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM match_run_facts WHERE run_id=?", (run_id,)).fetchone()[0]
        if existing:
            return
        for index, fact in enumerate(facts, start=1):
            conn.execute("""
                INSERT INTO match_run_facts (
                    run_id, fact_code, kind, label, value, source, source_ref, as_of,
                    status, affects, action, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, fact.get("fact_code") or f"E{index:02d}", fact["kind"], fact["label"], fact["value"],
                fact["source"], fact.get("source_ref", ""), fact.get("as_of", ""), fact["status"],
                fact.get("affects", ""), fact.get("action", ""), now, now,
            ))


def get_match_run_fact(run_id: int, fact_id: int):
    with db() as conn:
        if not _table_exists(conn, "match_run_facts"):
            return None
        return conn.execute("SELECT * FROM match_run_facts WHERE run_id=? AND id=?", (run_id, fact_id)).fetchone()


def update_match_run_fact(run_id: int, fact_id: int, *, status: str, value: str, reason: str):
    ensure_match_run_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as conn:
        before = conn.execute("SELECT * FROM match_run_facts WHERE run_id=? AND id=?", (run_id, fact_id)).fetchone()
        if not before:
            return None
        conn.execute("""
            UPDATE match_run_facts SET status=?, value=?, updated_at=? WHERE id=?
        """, (status, value, now, fact_id))
        conn.execute("""
            INSERT INTO match_run_revisions (
                run_id, fact_id, old_status, new_status, old_value, new_value, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, fact_id, before["status"], status, before["value"], value, reason, now))
        conn.execute("UPDATE match_runs SET updated_at=? WHERE id=?", (now, run_id))
        return conn.execute("SELECT * FROM match_run_facts WHERE id=?", (fact_id,)).fetchone()


def list_match_run_revisions(run_id: int, limit: int = 20):
    with db() as conn:
        if not _table_exists(conn, "match_run_revisions"):
            return []
        return conn.execute("""
            SELECT * FROM match_run_revisions WHERE run_id=? ORDER BY id DESC LIMIT ?
        """, (run_id, limit)).fetchall()


def update_match_run_state(run_id: int, *, phase: str | None = None, result_unlocked: bool | None = None,
                           judgment: dict | None = None):
    ensure_match_run_tables()
    assignments: list[str] = ["updated_at=?"]
    params: list[object] = [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    if phase is not None:
        assignments.append("phase=?")
        params.append(phase)
    if result_unlocked is not None:
        assignments.append("result_unlocked=?")
        params.append(1 if result_unlocked else 0)
    if judgment is not None:
        assignments.extend((
            "virtual_direction=?", "virtual_reasons=?", "virtual_handling=?", "virtual_change_conditions=?",
        ))
        params.extend((judgment["direction"], judgment["reasons"], judgment["handling"], judgment["change_conditions"]))
    params.append(run_id)
    with db() as conn:
        conn.execute(f"UPDATE match_runs SET {', '.join(assignments)} WHERE id=?", params)
        return conn.execute("SELECT * FROM match_runs WHERE id=?", (run_id,)).fetchone()


def get_score_schedule(identity: dict):
    """Read the ScoreGG-imported schedule row without falling back to files or HTTP."""
    with db() as conn:
        try:
            return conn.execute("""
                SELECT date, time_bjt, team_a, team_b, region, format, stage, source, updated_at
                FROM schedules
                WHERE date=? AND team_a=? AND team_b=?
                ORDER BY CASE WHEN time_bjt=? THEN 0 ELSE 1 END, updated_at DESC LIMIT 1
            """, (identity["match_date"], identity["team_a"], identity["team_b"], f'{identity["match_date"]} {identity["match_time"]}:00')).fetchone()
        except sqlite3.OperationalError:
            return None


def find_schedule_for_pair(team_a: str, team_b: str):
    """按对阵双方查找数据库中最新的赛程行（不限日期、不分主客顺序）。

    用于调用方未给出具体日期/时间时补全真实赛程，避免把缺省值当成“今天 00:00”造出幽灵场次。
    """
    with db() as conn:
        try:
            return conn.execute("""
                SELECT date, time_bjt, team_a, team_b, region, format, stage, source, updated_at
                FROM schedules
                WHERE (team_a=? AND team_b=?) OR (team_a=? AND team_b=?)
                ORDER BY date DESC, time_bjt DESC LIMIT 1
            """, (team_a, team_b, team_b, team_a)).fetchone()
        except sqlite3.OperationalError:
            return None


def get_score_result(identity: dict):
    with db() as conn:
        try:
            return conn.execute("""
                SELECT match_id, team_a_id, team_b_id, match_time, game_format, status, winner,
                       score_a, score_b, updated_at, stage
                FROM matches
                WHERE ((team_a_id=? AND team_b_id=?) OR (team_a_id=? AND team_b_id=?))
                  AND date(match_time)=?
                ORDER BY CASE WHEN team_a_id=? AND team_b_id=? THEN 0 ELSE 1 END,
                         match_time DESC, updated_at DESC LIMIT 1
            """, (
                identity["team_a"], identity["team_b"], identity["team_b"], identity["team_a"],
                identity["match_date"], identity["team_a"], identity["team_b"],
            )).fetchone()
        except sqlite3.OperationalError:
            return None


def list_score_results(*, team: str = "", date_from: str = "", date_to: str = "", limit: int = 20):
    """List completed ScoreGG results for natural date/team collection."""
    clauses = ["status='completed'"]
    params: list[object] = []
    if team:
        clauses.append("(team_a_id=? OR team_b_id=?)")
        params.extend((team, team))
    if date_from:
        clauses.append("date(match_time)>=?")
        params.append(date_from)
    if date_to:
        clauses.append("date(match_time)<=?")
        params.append(date_to)
    params.append(limit)
    with db() as conn:
        try:
            return conn.execute(f"""
                SELECT match_id, team_a_id, team_b_id, league_id, match_time, game_format, status,
                       winner, score_a, score_b, updated_at, stage
                FROM matches
                WHERE {' AND '.join(clauses)}
                ORDER BY match_time DESC, updated_at DESC LIMIT ?
            """, params).fetchall()
        except sqlite3.OperationalError:
            return []


def list_score_team_form(team: str, cutoff_at: str, limit: int = 5, match_format: str = "", league_id: str = ""):
    clauses = ["(team_a_id=? OR team_b_id=?)", "match_time < ?", "status='completed'"]
    params: list[object] = [team, team, cutoff_at]
    if str(match_format or "").upper():
        clauses.append("UPPER(game_format)=?")
        params.append(str(match_format).upper())
    if league_id:
        clauses.append("league_id=?")
        params.append(league_id)
    params.append(limit)
    with db() as conn:
        try:
            return conn.execute(f"""
                SELECT match_id, team_a_id, team_b_id, match_time, winner, score_a, score_b, game_format, stage
                FROM matches WHERE {' AND '.join(clauses)}
                ORDER BY match_time DESC LIMIT ?
            """, params).fetchall()
        except sqlite3.OperationalError:
            return []
