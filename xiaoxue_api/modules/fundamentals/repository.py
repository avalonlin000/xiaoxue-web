from __future__ import annotations

from contextlib import closing

from xiaoxue_api.core.database import connect


def list_team_rows(scope: str, limit: int):
    where, params = _scope_where(scope)
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
                   seed.outright_odds_decimal,
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
                   seed.final_seed_mu, seed.seed_sigma, seed.seed_ts,
                   seed.outright_odds_decimal, seed.note
            FROM teams t
            LEFT JOIN msi_ts_seed seed ON seed.team = t.short_name
            WHERE UPPER(t.short_name) = ?
               OR UPPER(t.name) = ?
               OR UPPER(seed.display_name) = ?
            LIMIT 1
            """,
            (code, code, code),
        ).fetchone()


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
