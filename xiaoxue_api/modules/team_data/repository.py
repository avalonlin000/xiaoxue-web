from __future__ import annotations

from datetime import date

from xiaoxue_api.core.database import connect


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
        row = conn.execute(
            "SELECT id FROM team_3d_data WHERE team_name=? ORDER BY updated_at DESC LIMIT 1",
            (team.upper(),),
        ).fetchone()
        if not row:
            return False
        conn.execute("""UPDATE team_3d_data
            SET dim_1_value=?, dim_2_value=?, dim_3_value=?, notes=?,
                version_understanding=?, updated_at=? WHERE id=?""",
            (
                values.get("dim_1_value", ""), values.get("dim_2_value", ""),
                values.get("dim_3_value", ""), values.get("notes", ""),
                values.get("version_understanding", ""), updated_at, row["id"],
            ),
        )
        return True


def get_profile_bundle(team: str):
    code = (team or "").strip().upper()
    with connect() as conn:
        row = conn.execute("""
            SELECT t.short_name, t.name, t.team_id, t.region, t.league_id, t.mu, t.sigma,
                   seed.final_seed_mu, seed.seed_sigma, seed.seed_ts,
                   seed.outright_odds_decimal, seed.note
            FROM teams t LEFT JOIN msi_ts_seed seed ON seed.team=t.short_name
            WHERE UPPER(t.short_name)=? OR UPPER(t.name)=? OR UPPER(seed.display_name)=?
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
    return row, d3, players
