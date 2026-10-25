"""只读事实读取：范围赛程、结果、队伍、首发与画像。

本模块只做 SELECT；不建表、不写入、不产生第二份正源。
"""
from __future__ import annotations

import sqlite3

from xiaoxue_api.core.database import connect


def list_schedules_between(date_from: str, date_to: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT date, time_bjt, team_a, team_b, region, format, stage, source, updated_at
               FROM schedules WHERE date BETWEEN ? AND ? ORDER BY date, time_bjt, id""",
            (date_from, date_to),
        ).fetchall()
    return [dict(row) for row in rows]


def scope_window() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT MIN(date) AS first_date, MAX(date) AS last_date FROM schedules").fetchone()
    return dict(row) if row else {"first_date": "", "last_date": ""}


def list_matches_by_ids(match_ids: list[str]) -> dict[str, dict]:
    if not match_ids:
        return {}
    placeholders = ",".join("?" for _ in match_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT match_id, team_a_id, team_b_id, match_time, status, winner,
                       score_a, score_b, created_at
                FROM matches WHERE match_id IN ({placeholders})""",
            tuple(match_ids),
        ).fetchall()
    return {str(row["match_id"]): dict(row) for row in rows}


def team_index() -> dict[str, dict]:
    """按简称和全名建立同一份队伍索引；一个名字同时命中两支队时按简称优先。"""
    with connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(teams)")}
        provenance = [
            column
            for column in ("source_kind", "source_ref", "source_updated_at", "verified_at")
            if column in columns
        ]
        selected = ", ".join(["team_id", "name", "short_name", "region", "league_id", "updated_at", *provenance])
        rows = conn.execute(f"SELECT {selected} FROM teams").fetchall()
    index: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        item.setdefault("source_kind", "")
        item.setdefault("source_ref", "")
        item.setdefault("source_updated_at", "")
        item.setdefault("verified_at", "")
        for key in (str(item.get("short_name") or "").strip(), str(item.get("name") or "").strip()):
            if key and key.casefold() not in index:
                index[key.casefold()] = item
    return index


def latest_starters(team_ids: list[str]) -> dict[str, dict]:
    if not team_ids:
        return {}
    placeholders = ",".join("?" for _ in team_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT team_id, COUNT(*) AS starter_count,
                       MAX(COALESCE(NULLIF(updated_at, ''), created_at)) AS updated_at
                FROM rosters
                WHERE team_id IN ({placeholders})
                  AND is_starter = 1
                  AND COALESCE(status, '') != 'inactive'
                  AND COALESCE(leave_date, '') = ''
                GROUP BY team_id""",
            tuple(team_ids),
        ).fetchall()
    return {str(row["team_id"]): dict(row) for row in rows}


def profile_updates(team_names: list[str]) -> dict[str, str]:
    if not team_names:
        return {}
    placeholders = ",".join("?" for _ in team_names)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT team_name, updated_at FROM team_profiles WHERE team_name IN ({placeholders})",
            tuple(team_names),
        ).fetchall()
    return {str(row["team_name"]): str(row["updated_at"] or "") for row in rows}


def has_price_source() -> bool:
    """LOL 价格来源是否已接入；S4 之前恒为 False（不做假数据）。"""
    with connect() as conn:
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM lol_price_facts",
            ).fetchone()
        except sqlite3.DatabaseError:
            return False
    return bool(row and row[0])


def latest_prices() -> dict[tuple[str, str], dict]:
    """每对队伍的最新报价（只读外部价格留存表）。"""
    with connect() as conn:
        try:
            rows = conn.execute(
                """SELECT team_a, team_b, market, price_a, price_b, source_kind, source_ref, recorded_at
                   FROM lol_price_facts ORDER BY id"""
            ).fetchall()
        except sqlite3.DatabaseError:
            return {}
    latest: dict[tuple[str, str], dict] = {}
    for row in rows:
        item = dict(row)
        latest[(str(item["team_a"]).casefold(), str(item["team_b"]).casefold())] = item
        latest[(str(item["team_b"]).casefold(), str(item["team_a"]).casefold())] = item
    return latest
