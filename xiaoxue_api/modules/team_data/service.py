from __future__ import annotations

from datetime import datetime
import json

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


def project_team_profile_to_3d(team: str, values: dict) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not repository.update_team_3d(team, values, now):
        raise TeamNotFound("队伍未找到")
    return {"ok": True, "updated_at": now}


def update_team_3d(team: str, values: dict) -> dict:
    raise ValueError("三维已并入队伍画像，只能更新队伍定位、怎么赢、怎么输、关键点或 BP 倾向")


def get_profile_bundle(team: str) -> dict | None:
    bundle = repository.get_profile_bundle(team)
    if not bundle:
        return None
    row, d3, players, profile = bundle
    return {
        "team": dict(row),
        "three_dimensional": dict(d3) if d3 else None,
        "team_profile": _profile_dict(profile),
        "players": [{
            "name": player["player_name"] or "暂无数据",
            "role": player["role"] or player["position"] or "位置暂无数据",
            "status": "首发" if player["is_starter"] else "轮换/替补",
        } for player in players],
    }


def _profile_dict(row) -> dict | None:
    if not row:
        return None
    result = dict(row)
    try:
        result["evidence"] = json.loads(result.pop("evidence_json") or "[]")
    except (TypeError, ValueError):
        result["evidence"] = []
        result.pop("evidence_json", None)
    return result


def get_team_profile(team: str) -> dict:
    bundle = get_profile_bundle(team)
    if not bundle:
        raise TeamNotFound("队伍未找到")
    profile = bundle.get("team_profile")
    if not profile:
        raise TeamNotFound(f"队伍 {team} 暂无统一画像")
    return profile


def update_team_profile(team: str, values: dict) -> dict:
    required = ("positioning", "win_path", "lose_path", "key_points", "bp_tendency")
    values = dict(values)
    existing = None
    try:
        existing = get_team_profile(team)
    except TeamNotFound:
        existing = None
    merged = {field: values.get(field, (existing or {}).get(field, "")) for field in required}
    if not any(str(value).strip() for value in values.values() if value is not None):
        raise ValueError("至少提供一项要更新的队伍画像内容")
    values.update(merged)
    if "evidence" in values:
        values["evidence_json"] = json.dumps(values.pop("evidence"), ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not repository.upsert_team_profile(team, values, now):
        raise TeamNotFound("队伍未找到")
    profile = get_team_profile(team)
    project_team_profile_to_3d(team, {
        "dim_1_name": "怎么赢", "dim_1_value": profile["win_path"],
        "dim_2_name": "怎么输", "dim_2_value": profile["lose_path"],
        "dim_3_name": "关键点", "dim_3_value": profile["key_points"],
    })
    _invalidate_teams_cache()
    return profile


def _invalidate_teams_cache() -> None:
    """队伍画像/3D 更新后失效 fundamentals 列表缓存（延迟 import 防循环）。"""
    try:
        from xiaoxue_api.modules.fundamentals.public import invalidate_teams_cache
    except ImportError:
        return
    invalidate_teams_cache()
