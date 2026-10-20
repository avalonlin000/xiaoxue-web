from __future__ import annotations

from datetime import date

from xiaoxue_api.core.database import connect


TEAM_PROFILE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_profiles (
    team_name TEXT PRIMARY KEY NOT NULL,
    region TEXT NOT NULL,
    positioning TEXT NOT NULL DEFAULT '',
    win_path TEXT NOT NULL DEFAULT '',
    lose_path TEXT NOT NULL DEFAULT '',
    key_points TEXT NOT NULL DEFAULT '',
    bp_tendency TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    format_version TEXT NOT NULL DEFAULT '1.0',
    updated_at TEXT NOT NULL
)
"""


def _ensure_team_profile_table(conn) -> None:
    conn.execute(TEAM_PROFILE_TABLE_SQL)


def list_teams():
    with connect() as conn:
        return conn.execute("""
            SELECT DISTINCT t.short_name, t.name, t.team_id, t.region
            FROM teams t
            WHERE EXISTS (SELECT 1 FROM rosters r WHERE r.team_id=t.team_id AND r.status='active')
               OR t.region='INTL'
               OR t.league_id LIKE 'MSI%'
               OR EXISTS (SELECT 1 FROM team_3d_data d WHERE d.team_name=t.short_name)
            ORDER BY CASE WHEN t.region='LPL' THEN 0 WHEN t.region='LCK' THEN 1
                          WHEN t.region='INTL' THEN 2 ELSE 3 END, t.short_name
        """).fetchall()


def list_schedules(filters: dict, limit: int):
    wheres, params = [], []
    event = filters.get("event")
    if event:
        event_like = f"%{event}%"
        if event.upper() == "MSI" or "季中赛" in event:
            wheres.append("(stage LIKE ? OR region=? OR source LIKE ?)")
            params.extend([event_like, "国际", event_like])
        else:
            wheres.append("stage LIKE ?")
            params.append(event_like)
    if filters.get("region"):
        wheres.append("region=?")
        params.append(filters["region"])
    if filters.get("team"):
        wheres.append("(team_a=? OR team_b=?)")
        params.extend([filters["team"], filters["team"]])
    if filters.get("date_from"):
        wheres.append("date>=?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        wheres.append("date<=?")
        params.append(filters["date_to"])
    if filters.get("upcoming"):
        wheres.append("date>=?")
        params.append(date.today().isoformat())
    where = " AND ".join(wheres) if wheres else "1=1"
    with connect() as conn:
        return conn.execute(
            f"""SELECT date, time_bjt, team_a, team_b, region, format, stage, updated_at
                FROM schedules WHERE {where}
                ORDER BY date ASC, time_bjt ASC LIMIT ?""",
            params + [limit],
        ).fetchall()


def get_team_id(short_name: str):
    with connect() as conn:
        return conn.execute("SELECT team_id FROM teams WHERE short_name=?", (short_name,)).fetchone()


def list_players(team_id: str):
    with connect() as conn:
        return conn.execute("""
            SELECT player_name, role FROM rosters
            WHERE team_id=? AND status='active' AND is_starter=1
            ORDER BY CASE role WHEN '上单' THEN 1 WHEN '打野' THEN 2 WHEN '中单' THEN 3
                     WHEN 'ADC' THEN 4 WHEN '辅助' THEN 5 END
        """, (team_id,)).fetchall()


def get_team_3d(team: str):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM team_3d_data WHERE team_name=? ORDER BY updated_at DESC LIMIT 1",
            (team.upper(),),
        ).fetchone()


def update_team_3d(team: str, values: dict, updated_at: str) -> bool:
    with connect() as conn:
        team_code = team.upper()
        row = conn.execute(
            "SELECT id FROM team_3d_data WHERE team_name=? ORDER BY updated_at DESC LIMIT 1",
            (team_code,),
        ).fetchone()
        if not row:
            team_row = conn.execute("SELECT region FROM teams WHERE short_name=? LIMIT 1", (team_code,)).fetchone()
            if not team_row:
                return False
            conn.execute("""INSERT INTO team_3d_data
                (team_name, region, dim_1_name, dim_1_value, dim_2_name, dim_2_value,
                 dim_3_name, dim_3_value, season, updated_at, notes, version_understanding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (team_code, team_row['region'], values.get('dim_1_name', '优势局习惯'), values.get('dim_1_value', ''),
                 values.get('dim_2_name', '劣势局习惯'), values.get('dim_2_value', ''),
                 values.get('dim_3_name', '胜负手位置'), values.get('dim_3_value', ''),
                 values.get('season', '2026 Spring'), updated_at, values.get('notes', ''),
                 values.get('version_understanding', '')),
            )
            return True
        conn.execute("""UPDATE team_3d_data
            SET dim_1_name=COALESCE(NULLIF(?, ''), dim_1_name),
                dim_1_value=COALESCE(NULLIF(?, ''), dim_1_value),
                dim_2_name=COALESCE(NULLIF(?, ''), dim_2_name),
                dim_2_value=COALESCE(NULLIF(?, ''), dim_2_value),
                dim_3_name=COALESCE(NULLIF(?, ''), dim_3_name),
                dim_3_value=COALESCE(NULLIF(?, ''), dim_3_value),
                notes=COALESCE(NULLIF(?, ''), notes),
                version_understanding=COALESCE(NULLIF(?, ''), version_understanding),
                updated_at=? WHERE id=?""",
            (values.get('dim_1_name', ''), values.get('dim_1_value', ''),
             values.get('dim_2_name', ''), values.get('dim_2_value', ''),
             values.get('dim_3_name', ''), values.get('dim_3_value', ''),
             values.get('notes', ''), values.get('version_understanding', ''), updated_at, row['id']),
        )
        return True


def get_profile_bundle(team: str):
    code = (team or "").strip().upper()
    with connect() as conn:
        row = conn.execute("""
            SELECT t.short_name, t.name, t.team_id, t.region, t.league_id, t.mu, t.sigma,
                   seed.final_seed_mu, seed.seed_sigma, seed.seed_ts, seed.note
            FROM teams t LEFT JOIN msi_ts_seed seed ON seed.team=t.short_name
            WHERE t.short_name=? OR UPPER(t.name)=? OR UPPER(seed.display_name)=?
            LIMIT 1
        """, (code, code, code)).fetchone()
        if not row:
            return None
        d3 = conn.execute("""
            SELECT dim_1_name, dim_1_value, dim_2_name, dim_2_value,
                   dim_3_name, dim_3_value, notes, version_understanding, updated_at
            FROM team_3d_data WHERE team_name=? ORDER BY updated_at DESC LIMIT 1
        """, (row["short_name"],)).fetchone()
        players = conn.execute("""
            SELECT player_name, role, position, is_starter, status FROM rosters
            WHERE team_id=? AND status='active'
            ORDER BY is_starter DESC, player_name LIMIT 8
        """, (row["team_id"],)).fetchall()
        has_profile_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='team_profiles'").fetchone()
        profile = conn.execute(
            "SELECT * FROM team_profiles WHERE team_name=?",
            (row["short_name"],),
        ).fetchone() if has_profile_table else None
    return row, d3, players, profile


def upsert_team_profile(team: str, values: dict, updated_at: str) -> bool:
    code = (team or "").strip().upper()
    fields = ("positioning", "win_path", "lose_path", "key_points", "bp_tendency")
    with connect() as conn:
        _ensure_team_profile_table(conn)
        team_row = conn.execute(
            "SELECT short_name, region FROM teams WHERE short_name=? LIMIT 1",
            (code,),
        ).fetchone()
        if not team_row:
            return False
        current = conn.execute(
            "SELECT * FROM team_profiles WHERE team_name=?",
            (team_row["short_name"],),
        ).fetchone()
        merged = {
            field: values.get(field) if values.get(field) is not None
            else (current[field] if current else "")
            for field in fields
        }
        evidence_json = values.get("evidence_json")
        if evidence_json is None:
            evidence_json = current["evidence_json"] if current else "[]"
        conn.execute(
            """INSERT INTO team_profiles
               (team_name, region, positioning, win_path, lose_path, key_points,
                bp_tendency, evidence_json, format_version, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, '1.0', ?)
               ON CONFLICT(team_name) DO UPDATE SET
                 region=excluded.region, positioning=excluded.positioning,
                 win_path=excluded.win_path, lose_path=excluded.lose_path,
                 key_points=excluded.key_points, bp_tendency=excluded.bp_tendency,
                 evidence_json=excluded.evidence_json,
                 format_version=excluded.format_version, updated_at=excluded.updated_at""",
            (
                team_row["short_name"], team_row["region"],
                *(str(merged[field] or "").strip() for field in fields),
                str(evidence_json), updated_at,
            ),
        )
        return True
