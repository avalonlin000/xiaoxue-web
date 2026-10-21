from __future__ import annotations

import re
import time

from xiaoxue_api.modules.profiles.public import get_wiki_team
from xiaoxue_api.modules.tk_knowledge.public import count_team_entries

from . import repository


class TeamsNotFound(LookupError):
    pass


# list_teams 热路径会逐队读 Wiki/TK 文档（31 次/请求），用 TTL 缓存兜住高频访问。
# 队伍画像/3D/TK 更新接口会显式 invalidate；TTL 作为兜底保证最多 _CACHE_TTL 秒旧。
_CACHE_TTL = 120.0
_teams_cache: dict[str, tuple[float, dict]] = {}


def invalidate_teams_cache() -> None:
    _teams_cache.clear()


def list_teams(scope: str = "all", limit: int = 80, team: str = "") -> dict:
    key = f"{scope}:{limit}:{team}"
    now = time.monotonic()
    hit = _teams_cache.get(key)
    if hit is not None and now - hit[0] < _CACHE_TTL:
        return hit[1]
    result = _list_teams_uncached(scope, limit, team)
    _teams_cache[key] = (now, result)
    return result


def _list_teams_uncached(scope: str = "all", limit: int = 80, team: str = "") -> dict:
    rows = repository.list_team_rows(scope, limit, team)
    stage_name = repository.active_stage()
    stage_ts = repository.get_stage_ts_snapshot_map(stage_name)
    baseline_map = repository.get_regular_baseline_map(stage_name)
    stage_display = repository.get_stage_display_map(stage_name)
    cycle_signals = repository.get_stage_cycle_signal_map(stage_name)
    starters_by_team = repository.list_starters_by_team([row["team_id"] for row in rows])
    is_msi = (scope or "").lower() == "msi"
    teams = []
    for row in rows:
        code = row["short_name"]
        profile_markdown = _profile_markdown(code)
        has_profile = bool(profile_markdown)
        tk_count = _tk_count(code)
        has_3d = bool(row["dim_1_value"] or row["dim_2_value"] or row["dim_3_value"])
        players = _starter_cards(starters_by_team.get(row["team_id"], []))
        ts_row = stage_ts.get(code.upper())
        baseline_row = baseline_map.get(code.upper())
        display_row = stage_display.get(code.upper())
        cycle_row = cycle_signals.get(code.upper())
        if has_profile and has_3d and tk_count:
            quality = "完整"
        elif has_profile or has_3d or tk_count:
            quality = "部分"
        else:
            quality = "资料不足"
        # TS 唯一正源：ts_stage_snapshots 底表 + ts_stage_display 展示层。
        seed_mu = row["final_seed_mu"] if is_msi else None
        seed_sigma = row["seed_sigma"] if is_msi else None
        seed_ts = row["seed_ts"] if is_msi else None
        teams.append({
            "short_name": code,
            "name": row["name"] or code,
            "team_id": row["team_id"],
            "region": row["region"] or "",
            "league_id": row["league_id"] or "",
            "mu": ts_row["mu"] if ts_row else (row["mu"] or 25),
            "sigma": ts_row["sigma"] if ts_row else (row["sigma"] or 8.333),
            "ts_score": round(ts_row["ts"] if ts_row else (row["mu"] or 25) - 3 * (row["sigma"] or 8.333), 3),
            "ts_stage": stage_name if ts_row else "legacy",
            "ts_l1": ({"rank": ts_row["rank"], "tier": ts_row["tier"], "conclusion_score": ts_row["conclusion_score"]} if ts_row else None),
            "ts_l2": ({"strength_score": ts_row["strength_score"], "stability_score": ts_row["stability_score"], "mu": ts_row["mu"], "sigma": ts_row["sigma"], "ts": ts_row["ts"], "matches": ts_row["matches"], "wins": ts_row["wins"]} if ts_row else None),
            "ts_display": ({
                "power_score": display_row["power_score"],
                "volatility_score": display_row["volatility_score"],
                "trend": display_row["trend"],
                "momentum": display_row["momentum"],
                "status": display_row["status"],
                "cycle": ({
                    "cycle_type": cycle_row["cycle_type"],
                    "cycle_stage": cycle_row["cycle_stage"],
                    "focus_signal": cycle_row["focus_signal"],
                    "focus_priority": cycle_row["focus_priority"],
                    "signal_reason": cycle_row["signal_reason"],
                    "confirmation_needed": cycle_row["confirmation_needed"],
                } if cycle_row else None),
            } if display_row else None),
            "ts_context": {"regular_baseline": (
                {"available": True, "matches": baseline_row["matches"], "wins": baseline_row["wins"], "updated_at": baseline_row["updated_at"]}
                if baseline_row else {"available": False}
            )},
            "seed_mu": seed_mu,
            "seed_sigma": seed_sigma,
            "seed_ts": seed_ts,
            "has_profile": has_profile,
            "has_3d": has_3d,
            "has_tk": tk_count > 0,
            "tk_count": tk_count,
            "players": players,
            "players_note": "首发/关键选手来自 rosters；缺数据不推断" if players else "资料缺口/暂无数据",
            "dim_1_name": row["dim_1_name"] or "优势局",
            "dim_1_value": row["dim_1_value"] or "-",
            "dim_2_name": row["dim_2_name"] or "劣势局",
            "dim_2_value": row["dim_2_value"] or "-",
            "dim_3_name": row["dim_3_name"] or "胜负手",
            "dim_3_value": row["dim_3_value"] or "-",
            "notes_summary": _text_summary(row["notes"] or profile_markdown, 110),
            "version_summary": "",
            "updated_at": row["updated_at"] or "",
            "data_quality": quality,
        })
    return {"scope": scope, "teams": teams}


def get_msi() -> dict:
    teams = list_teams(scope="msi", limit=120)["teams"]
    regions = {}
    missing_profiles = []
    missing_3d = []
    for team in teams:
        region = team["region"] or "UNKNOWN"
        regions[region] = regions.get(region, 0) + 1
        if not team["has_profile"]:
            missing_profiles.append(team["short_name"])
        if not team["has_3d"]:
            missing_3d.append(team["short_name"])
    return {
        "event": "MSI",
        "positioning": "国际赛环境研究，不是赛程表",
        "teams": teams,
        "regions": regions,
        "missing_profiles": missing_profiles,
        "missing_3d": missing_3d,
        "key_topics": ["跨赛区强弱", "外卡未知量", "版本理解差", "BO 稳定性", "资料缺口"],
    }


def get_ts_updates(team: str, limit: int = 20, days: int = 30) -> dict:
    return repository.list_ts_updates(team, limit, days)


def get_match_context(team_a: str, team_b: str, *, event: str = "") -> dict:
    row_a = repository.get_ts_team(team_a)
    row_b = repository.get_ts_team(team_b)
    if not row_a or not row_b:
        missing = [name for name, row in ((team_a, row_a), (team_b, row_b)) if not row]
        raise TeamsNotFound(f"TS 底表未找到队伍：{', '.join(missing)}")
    display_map = repository.get_stage_display_map()
    cycle_map = repository.get_stage_cycle_signal_map()
    prefer_msi_seed = _prefers_msi_seed(event)
    context_a = _ts_team_context(row_a, prefer_msi_seed=prefer_msi_seed, display_row=display_map.get(str(row_a["short_name"]).upper()), cycle_row=cycle_map.get(str(row_a["short_name"]).upper()))
    context_b = _ts_team_context(row_b, prefer_msi_seed=prefer_msi_seed, display_row=display_map.get(str(row_b["short_name"]).upper()), cycle_row=cycle_map.get(str(row_b["short_name"]).upper()))
    if not context_a or not context_b:
        raise TeamsNotFound(f"TS 底表未找到队伍：{', '.join(name for name, ctx in ((team_a, context_a), (team_b, context_b)) if not ctx)}")
    return {
        "event": "MSI" if prefer_msi_seed else (event or "当前队伍 TS"),
        "team_a": context_a,
        "team_b": context_b,
        "compare": _build_match_context(context_a, context_b),
    }


def _profile_markdown(team: str) -> str:
    try:
        profile = get_wiki_team(team)
    except (OSError, RuntimeError):
        return ""
    return profile.get("markdown", "") if profile.get("found") else ""


def _tk_count(team: str) -> int:
    try:
        return count_team_entries(team)
    except (OSError, RuntimeError):
        return 0


def _starter_cards(rows) -> list[dict]:
    return [{
        "name": row["player_name"] or "暂无数据",
        "role": row["role"] or row["position"] or "位置暂无数据",
        "status": "首发" if row["is_starter"] else "轮换/替补",
    } for row in rows]


def _text_summary(text: str, limit: int = 96) -> str:
    cleaned = re.sub(r"[#>*`\[\]_|-]+", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _formatted(value, digits: int = 1) -> str:
    return f"{_number(value):.{digits}f}"


def _prefers_msi_seed(event: str) -> bool:
    normalized = str(event or "").strip().upper()
    return normalized == "MSI" or "季中赛" in normalized


def _ts_team_context(row, *, prefer_msi_seed: bool = False, display_row: dict | None = None,
                     cycle_row: dict | None = None) -> dict | None:
    if not row:
        return None
    has_seed = row["final_seed_mu"] is not None and row["seed_sigma"] is not None
    use_seed = prefer_msi_seed and has_seed
    mu = _number(row["final_seed_mu"] if use_seed else row["mu"], 25)
    sigma = _number(row["seed_sigma"] if use_seed else row["sigma"], 8.333)
    ts = _number(row["seed_ts"] if use_seed else None, mu - 3 * sigma)
    if sigma <= 1.2:
        volatility = "低波动"
    elif sigma <= 3.5:
        volatility = "中波动"
    elif sigma <= 5.2:
        volatility = "高波动"
    else:
        volatility = "极高波动"
    confidence = (
        "高样本"
        if (row["region"] or "") in {"LPL", "LCK"} and sigma <= 1.5
        else "中样本" if sigma <= 5.0 else "低样本"
    )
    # 展示层（处理后的 0-100 百分制）随比赛上下文一起给消费者；原始 mu/sigma/ts
    # 仅留在内部字段，用户界面一律使用 power_score/volatility_score 等展示值。
    display = display_row or {}
    return {
        "team": row["short_name"],
        "display_name": row["name"] or row["short_name"],
        "region": row["region"] or "",
        "mu": round(mu, 3),
        "sigma": round(sigma, 3),
        "ts": round(ts, 3),
        "risk_gap": round(mu - ts, 3),
        "volatility_tier": volatility,
        "sample_confidence": confidence,
        "power_score": display.get("power_score"),
        "volatility_score": display.get("volatility_score"),
        "trend": display.get("trend"),
        "momentum": display.get("momentum"),
        "status": display.get("status"),
        "cycle": ({
            "cycle_type": cycle_row.get("cycle_type"),
            "cycle_stage": cycle_row.get("cycle_stage"),
            "focus_signal": cycle_row.get("focus_signal"),
            "focus_priority": cycle_row.get("focus_priority"),
            "signal_reason": cycle_row.get("signal_reason"),
            "confirmation_needed": cycle_row.get("confirmation_needed"),
        } if cycle_row else None),
        "note": row["note"] or "",
        "source": "msi_seed" if use_seed else "team_ts",
    }


def _difference_line(label: str, value: float, strong_side: str, threshold: float = 0.0) -> str:
    if abs(value) <= threshold:
        return f"{label}接近"
    return f"{strong_side} {label}领先 {_formatted(abs(value))}"


def _build_match_context(team_a: dict, team_b: dict) -> dict:
    if not can_compare_team_ratings(team_a, team_b):
        reason = "跨赛区或赛区口径未核实，TS分数不能直接比较；只分别查看各队状态。"
        return {**dict.fromkeys(("mu_diff", "sigma_diff", "ts_diff", "power_diff", "stability_diff", "stronger", "more_volatile")),
                "comparable": False, "reason": reason, "power_note": reason,
                "volatility_note": "", "risk_note": reason, "daily_summary": reason}
    power_a = team_a.get("power_score")
    power_b = team_b.get("power_score")
    stability_a = team_a.get("volatility_score")
    stability_b = team_b.get("volatility_score")
    mu_diff = round(team_a["mu"] - team_b["mu"], 3)
    sigma_diff = round(team_a["sigma"] - team_b["sigma"], 3)
    ts_diff = round(team_a["ts"] - team_b["ts"], 3)
    # 用户界面只消费处理后的展示值：综合实力差 / 稳定性差。
    power_diff = round((power_a or 0) - (power_b or 0), 1) if power_a is not None and power_b is not None else None
    stability_diff = round((stability_a or 0) - (stability_b or 0), 1) if stability_a is not None and stability_b is not None else None
    stronger = team_a["team"] if mu_diff >= 0 else team_b["team"]
    weaker = team_b["team"] if mu_diff >= 0 else team_a["team"]
    if power_diff is not None and abs(power_diff) >= 25:
        power_note = f"{stronger} 综合实力明显领先，{weaker} 需要靠版本/BP/临场波动制造空间。"
    elif power_diff is not None and abs(power_diff) >= 10:
        power_note = f"{stronger} 综合实力有优势，但不是碾压档，仍要结合版本、BP 和临场状态判断。"
    else:
        power_note = "两队综合实力差不大，单场更看版本适配、BP 和当天状态。"
    if stability_diff is not None and abs(stability_diff) >= 20:
        more_stable = team_a["team"] if stability_diff >= 0 else team_b["team"]
        less_stable = team_b["team"] if stability_diff >= 0 else team_a["team"]
        volatility_note = f"{less_stable} 稳定性明显更低，上限/下限都更散；{more_stable} 更偏稳定兑现。"
    elif (stability_a or 0) <= 20 or (stability_b or 0) <= 20:
        volatility_note = "这场至少一边稳定性很低，日报里要提示爆冷风险，不要只看实力。"
    else:
        volatility_note = "两边稳定性都不差，TS 参考价值相对稳定。"

    daily_summary = (
        f"TS参考：{team_a['team']} 综合实力 {_formatted(power_a or 0)} / 稳定性 {_formatted(stability_a or 0)}；"
        f"{team_b['team']} 综合实力 {_formatted(power_b or 0)} / 稳定性 {_formatted(stability_b or 0)}。"
        f"{power_note}{volatility_note}"
    )
    risk_note = (
        f"关注点：{_difference_line('综合实力', power_diff or 0, stronger, 2.0)}；"
        f"{_difference_line('稳定性', stability_diff or 0, (team_a['team'] if (stability_diff or 0) >= 0 else team_b['team']), 2.0)}；"
        f"综合实力差 {_formatted(abs(power_diff or 0))} 偏向 {team_a['team'] if (power_diff or 0) >= 0 else team_b['team']}。"
    )
    return {
        "comparable": True,
        "mu_diff": mu_diff,
        "sigma_diff": sigma_diff,
        "ts_diff": ts_diff,
        "power_diff": power_diff,
        "stability_diff": stability_diff,
        "stronger": stronger,
        "more_volatile": team_b["team"] if (stability_diff or 0) < 0 else team_a["team"],
        "power_note": power_note,
        "volatility_note": volatility_note,
        "risk_note": risk_note,
        "daily_summary": daily_summary,
    }


def can_compare_team_ratings(team_a: dict, team_b: dict) -> bool:
    """The existing cycle method allows only a known, shared domestic scale."""
    return team_a.get("region") in {"LPL", "LCK"} and team_a.get("region") == team_b.get("region")
