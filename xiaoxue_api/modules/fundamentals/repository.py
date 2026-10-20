from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

from xiaoxue_api.core import database
from xiaoxue_api.core.database import connect


def list_team_rows(scope: str, limit: int, team: str = ""):
    where, params = _scope_where(scope)
    if team and team.strip():
        where = f"({where}) AND UPPER(t.short_name) = UPPER(?)"
        params = params + [team.strip()]
    order_by = (
        "seed.final_seed_mu DESC"
        if (scope or "").lower() == "msi"
        else "CASE WHEN t.region='LPL' THEN 0 WHEN t.region='LCK' THEN 1 "
             "WHEN t.region='INTL' THEN 2 ELSE 3 END, t.short_name"
    )
    with closing(connect()) as conn:
        return conn.execute(
            f"""
            SELECT t.short_name, t.name, t.team_id, t.region, t.league_id,
                   t.mu, t.sigma,
                   seed.final_seed_mu, seed.seed_sigma, seed.seed_ts,
                   d.dim_1_name, d.dim_1_value, d.dim_2_name, d.dim_2_value,
                   d.dim_3_name, d.dim_3_value, d.notes,
                   d.version_understanding, d.updated_at
            FROM teams t
            LEFT JOIN msi_ts_seed seed ON seed.team = t.short_name
            LEFT JOIN team_3d_data d ON d.id = (
                SELECT id FROM team_3d_data dd
                WHERE dd.team_name = t.short_name
                ORDER BY dd.updated_at DESC LIMIT 1
            )
            WHERE {where}
              AND t.status != 'retired'
              AND (t.short_name IS NOT NULL AND t.short_name != '')
            ORDER BY {order_by}
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()


def list_starters_by_team(team_ids: list[str]) -> dict[str, list]:
    identifiers = list(dict.fromkeys(team_id for team_id in team_ids if team_id))
    if not identifiers:
        return {}
    placeholders = ", ".join("?" for _ in identifiers)
    with closing(connect()) as conn:
        rows = conn.execute(
            f"""
            SELECT team_id, player_name, role, position, is_starter, status
            FROM rosters
            WHERE team_id IN ({placeholders}) AND status = 'active'
            ORDER BY team_id,
                     is_starter DESC,
                     CASE COALESCE(role, position)
                       WHEN '上单' THEN 1 WHEN 'TOP' THEN 1
                       WHEN '打野' THEN 2 WHEN 'JUNGLE' THEN 2
                       WHEN '中单' THEN 3 WHEN 'MID' THEN 3
                       WHEN 'ADC' THEN 4 WHEN 'BOT' THEN 4
                       WHEN '辅助' THEN 5 WHEN 'SUPPORT' THEN 5
                       ELSE 9 END,
                     player_name
            """,
            identifiers,
        ).fetchall()
    grouped = {team_id: [] for team_id in identifiers}
    for row in rows:
        values = grouped.setdefault(row["team_id"], [])
        if len(values) < 8:
            values.append(row)
    return grouped


def get_ts_team(team: str):
    code = (team or "").strip().upper()
    if not code:
        return None
    with closing(connect()) as conn:
        return conn.execute(
            """
            SELECT t.short_name, t.name, t.region, t.mu, t.sigma,
                   seed.final_seed_mu, seed.seed_sigma, seed.seed_ts, seed.note
            FROM teams t
            LEFT JOIN msi_ts_seed seed ON seed.team = t.short_name
            WHERE t.short_name = ?
               OR UPPER(t.name) = ?
               OR UPPER(seed.display_name) = ?
            LIMIT 1
            """,
            (code, code, code),
        ).fetchone()


_STAGE_TOKENS_CACHE: dict[str, str] | None = None


def _stage_tokens() -> dict[str, str]:
    """读取 lol_data system_config 的 stage tokens（单一事实源；失败时用内置默认）。"""
    global _STAGE_TOKENS_CACHE
    if _STAGE_TOKENS_CACHE is None:
        tokens = {"ts_default_stage": "第三赛段", "ts_intl_stage": "国际赛"}
        try:
            config_path = Path(database.DB_PATH).resolve().parent / "config" / "system_config.json"
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in (data.get("stage_tokens") or {}).items():
                if isinstance(value, str) and value:
                    tokens[key] = value
        except (OSError, json.JSONDecodeError):
            pass
        _STAGE_TOKENS_CACHE = tokens
    return _STAGE_TOKENS_CACHE


def active_stage() -> str:
    """当前活动 TS 阶段：国际赛一旦有快照即接管，否则读国内阶段（见 lol_data 双阶段设计）。"""
    tokens = _stage_tokens()
    default_stage = tokens.get("ts_default_stage") or "第三赛段"
    intl_stage = tokens.get("ts_intl_stage") or ""
    if not intl_stage or intl_stage == default_stage:
        return default_stage
    try:
        with closing(connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM ts_stage_snapshots WHERE stage=? LIMIT 1", (intl_stage,)
            ).fetchone()
    except sqlite3.OperationalError:
        return default_stage
    return intl_stage if row else default_stage


def get_stage_ts_snapshot_map(stage: str | None = None) -> dict[str, dict]:
    stage = stage or active_stage()
    try:
        with closing(connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM ts_stage_snapshots WHERE stage=?",
                (stage,),
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["team"]: dict(row) for row in rows}


def get_regular_baseline_map(stage: str | None = None) -> dict[str, dict]:
    """Read regular-season baseline metadata without exposing raw ratings."""
    stage = stage or active_stage()
    try:
        with closing(connect()) as conn:
            rows = conn.execute(
                "SELECT team, matches, wins, updated_at FROM ts_regular_baselines WHERE stage=?",
                (stage,),
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["team"]: dict(row) for row in rows}


def get_stage_display_map(stage: str | None = None) -> dict[str, dict]:
    """统一展示层：实力/波动/趋势/势头/状态。"""
    stage = stage or active_stage()
    try:
        with closing(connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM ts_stage_display WHERE stage=?",
                (stage,),
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["team"]: dict(row) for row in rows}


def get_stage_cycle_signal_map(stage: str | None = None) -> dict[str, dict]:
    stage = stage or active_stage()
    try:
        with closing(connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM ts_cycle_signals WHERE stage=?",
                (stage,),
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row["team"]: dict(row) for row in rows}


def list_ts_updates(team: str, limit: int, days: int) -> dict:
    """Read the append-only TS change history without touching any snapshot."""
    code = (team or "").strip().upper()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        with closing(connect()) as conn:
            rows = conn.execute(
                """
                SELECT stage, region, team, field, old_value, new_value,
                       trigger_source, updated_at
                FROM ts_update_log
                WHERE UPPER(team) = ? AND updated_at >= ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (code, cutoff, limit),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table: ts_update_log" not in str(exc):
            raise
        return {
            "team": code,
            "days": days,
            "updates": [],
            "status": "unavailable",
            "reason": "ts_update_log_not_initialized",
        }
    return {"team": code, "days": days, "updates": [dict(row) for row in rows]}


def _scope_where(scope: str) -> tuple[str, list]:
    normalized = (scope or "all").lower()
    if normalized == "lpl":
        return "t.region = ?", ["LPL"]
    if normalized == "lck":
        return "t.region = ?", ["LCK"]
    if normalized == "intl":
        return "t.region = ?", ["INTL"]
    if normalized == "msi":
        return "t.short_name IN (SELECT team FROM msi_ts_seed)", []
    return "1=1", []
