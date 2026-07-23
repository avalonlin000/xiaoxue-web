from __future__ import annotations

import re

from xiaoxue_api.modules.profiles.public import get_wiki_team
from xiaoxue_api.modules.tk_knowledge.public import count_team_entries

from . import repository


class TeamsNotFound(LookupError):
    pass


def list_teams(scope: str = "all", limit: int = 80) -> dict:
    rows = repository.list_team_rows(scope, limit)
    starters_by_team = repository.list_starters_by_team([row["team_id"] for row in rows])
    teams = []
    for row in rows:
        code = row["short_name"]
        profile_markdown = _profile_markdown(code)
        has_profile = bool(profile_markdown)
        tk_count = _tk_count(code)
        has_3d = bool(row["dim_1_value"] or row["dim_2_value"] or row["dim_3_value"])
        players = _starter_cards(starters_by_team.get(row["team_id"], []))
        if has_profile and has_3d and tk_count:
            quality = "完整"
        elif has_profile or has_3d or tk_count:
            quality = "部分"
        else:
            quality = "资料不足"
        teams.append({
            "short_name": code,
            "name": row["name"] or code,
            "team_id": row["team_id"],
            "region": row["region"] or "",
            "league_id": row["league_id"] or "",
            "mu": row["mu"],
            "sigma": row["sigma"],
            "ts_score": round((row["mu"] or 25) - 3 * (row["sigma"] or 8.333), 3),
            "odds": row["outright_odds_decimal"],
            "seed_mu": row["final_seed_mu"],
            "seed_sigma": row["seed_sigma"],
            "seed_ts": row["seed_ts"],
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


def get_match_context(team_a: str, team_b: str) -> dict:
    row_a = repository.get_ts_team(team_a)
    row_b = repository.get_ts_team(team_b)
    if not row_a or not row_b:
        missing = [name for name, row in ((team_a, row_a), (team_b, row_b)) if not row]
        raise TeamsNotFound(f"MSI TS 队伍未找到：{', '.join(missing)}")
    context_a = _ts_team_context(row_a)
    context_b = _ts_team_context(row_b)
    return {
        "event": "MSI",
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


def _ts_team_context(row) -> dict | None:
    if not row:
        return None
    mu = _number(row["final_seed_mu"], _number(row["mu"], 25))
    sigma = _number(row["seed_sigma"], _number(row["sigma"], 8.333))
    ts = _number(row["seed_ts"], mu - 3 * sigma)
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
    return {
        "team": row["short_name"],
        "display_name": row["name"] or row["short_name"],
        "region": row["region"] or "",
        "odds": row["outright_odds_decimal"],
        "mu": round(mu, 3),
        "sigma": round(sigma, 3),
        "ts": round(ts, 3),
        "risk_gap": round(mu - ts, 3),
        "volatility_tier": volatility,
        "sample_confidence": confidence,
        "note": row["note"] or "",
    }


def _difference_line(label: str, value: float, strong_side: str, threshold: float = 0.0) -> str:
    if abs(value) <= threshold:
        return f"{label}接近"
    return f"{strong_side} {label}领先 {_formatted(abs(value))}"


def _build_match_context(team_a: dict, team_b: dict) -> dict:
    mu_diff = round(team_a["mu"] - team_b["mu"], 3)
    sigma_diff = round(team_a["sigma"] - team_b["sigma"], 3)
    ts_diff = round(team_a["ts"] - team_b["ts"], 3)
    stronger = team_a["team"] if mu_diff >= 0 else team_b["team"]
    weaker = team_b["team"] if mu_diff >= 0 else team_a["team"]
    more_volatile = team_a["team"] if sigma_diff >= 0 else team_b["team"]
    less_volatile = team_b["team"] if sigma_diff >= 0 else team_a["team"]
    if abs(mu_diff) >= 4:
        power_note = f"{stronger} 绝对实力明显领先，{weaker} 需要靠版本/BP/临场波动制造空间。"
    elif abs(mu_diff) >= 2:
        power_note = f"{stronger} 实力有优势，但不是碾压档，盘口不能只按强弱简单处理。"
    else:
        power_note = "两队实力差不大，单场更看版本适配、BP 和当天状态。"
    if abs(sigma_diff) >= 2.5:
        volatility_note = f"{more_volatile} 波动明显更大，意味着上限/下限都更散；{less_volatile} 更偏稳定兑现。"
    elif max(team_a["sigma"], team_b["sigma"]) >= 4.5:
        volatility_note = "这场至少一边处于高波动区，日报里要提示爆冷/让盘风险，不要只看实力。"
    else:
        volatility_note = "两边波动都不高，TS 参考价值相对稳定。"
    market_note = "赔率只作市场位置参考：日报里重点对照实力差和波动差，判断市场有没有把强队热度或弱队爆冷空间打满。"
    daily_summary = (
        f"TS参考：{team_a['team']} mu {_formatted(team_a['mu'])} / σ {_formatted(team_a['sigma'])} / TS {_formatted(team_a['ts'])}；"
        f"{team_b['team']} mu {_formatted(team_b['mu'])} / σ {_formatted(team_b['sigma'])} / TS {_formatted(team_b['ts'])}。"
        f"{power_note}{volatility_note}"
    )
    risk_note = (
        f"关注点：{_difference_line('实力', mu_diff, stronger, 0.8)}；"
        f"{_difference_line('波动', sigma_diff, more_volatile, 0.4)}；"
        f"保守下界差 {_formatted(abs(ts_diff))} 偏向 {team_a['team'] if ts_diff >= 0 else team_b['team']}。"
    )
    return {
        "mu_diff": mu_diff,
        "sigma_diff": sigma_diff,
        "ts_diff": ts_diff,
        "stronger": stronger,
        "more_volatile": more_volatile,
        "power_note": power_note,
        "volatility_note": volatility_note,
        "market_note": market_note,
        "risk_note": risk_note,
        "daily_summary": daily_summary,
    }
