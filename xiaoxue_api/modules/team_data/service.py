from __future__ import annotations

from datetime import datetime

from . import repository


class TeamNotFound(LookupError):
    pass


def list_teams() -> list[dict]:
    return [dict(row) for row in repository.list_teams()]


def list_schedules(filters: dict, limit: int = 50) -> list[dict]:
    return [{
        "date": row["date"], "time": row["time_bjt"], "team_a": row["team_a"],
        "team_b": row["team_b"], "region": row["region"], "format": row["format"],
        "stage": row["stage"], "updated_at": row["updated_at"],
    } for row in repository.list_schedules(filters, limit)]


def list_players(team: str) -> list[dict]:
    team_row = repository.get_team_id(team)
    if not team_row:
        raise TeamNotFound("队伍未找到")
    return [{"name": row["player_name"], "role": row["role"]}
            for row in repository.list_players(team_row["team_id"])]


def get_team_3d(team: str) -> dict:
    row = repository.get_team_3d(team)
    if not row:
        raise TeamNotFound(f"队伍 {team} 无三维")
    return {
        "team_name": row["team_name"],
        "dim_1_name": row["dim_1_name"], "dim_1_value": row["dim_1_value"],
        "dim_2_name": row["dim_2_name"], "dim_2_value": row["dim_2_value"],
        "dim_3_name": row["dim_3_name"], "dim_3_value": row["dim_3_value"],
        "notes": row["notes"] or "", "version_understanding": row["version_understanding"] or "",
        "updated_at": row["updated_at"],
    }


def update_team_3d(team: str, values: dict) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not repository.update_team_3d(team, values, now):
        raise TeamNotFound("队伍未找到")
    return {"ok": True, "updated_at": now}


def get_profile_bundle(team: str) -> dict | None:
    bundle = repository.get_profile_bundle(team)
    if not bundle:
        return None
    row, d3, players = bundle
    return {
        "team": dict(row),
        "three_dimensional": dict(d3) if d3 else None,
        "players": [{
            "name": player["player_name"] or "暂无数据",
            "role": player["role"] or player["position"] or "位置暂无数据",
            "status": "首发" if player["is_starter"] else "轮换/替补",
        } for player in players],
    }
