"""LOL 范围派生与覆盖面计算（只读）。

- 范围唯一来源：current_event 的赛事配置（通过 public 入口读取，不复制第二份）。
- 覆盖面只计算事实，不写库；缺口统一进入结果合同的 gaps。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from xiaoxue_api.modules.match.event.public import (
    get_current_event,
    get_current_event_scope_leagues,
    match_in_current_event_scope,
)
from xiaoxue_api.modules.match.scope import repository

# 赛制时长上限：只用于判断"赛后多久还没结果才算洞"，不是开赛时间。
FORMAT_DURATION_HOURS = {"BO1": 1.5, "BO2": 3.0, "BO3": 3.5, "BO5": 5.0}
DEFAULT_DURATION_HOURS = 4.0

# 首发/画像陈旧阈值：显式声明并在输出里回传，避免隐式判断。
LINEUP_STALE_DAYS = 45
PROFILE_STALE_DAYS = 45
UNRESOLVED = {"", "tbd", "待定", "-"}


class ScopeUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now()


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if len(text) > 19 else text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_days(value: str, now: datetime) -> int | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0, (now - parsed).days)


def _is_unresolved(name: str) -> bool:
    return str(name or "").strip().casefold() in UNRESOLVED


def _match_key(source: object) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    if ":" in text:
        return "scoregg_" + text.split(":", 1)[1].strip()
    return text


def _scope_schedules(leagues: list[str], date_from: str = "", date_to: str = "") -> list[dict]:
    window = repository.scope_window()
    start = date_from or str(window.get("first_date") or "")
    end = date_to or str(window.get("last_date") or "")
    if not start or not end:
        return []
    rows = repository.list_schedules_between(start, end)
    return [row for row in rows if match_in_current_event_scope(row, leagues)]


def _lineup_state(side: str, team: dict | None, starters: dict, now: datetime, match_unresolved: bool) -> dict:
    if match_unresolved:
        return {"status": "pending", "detail": "对阵未定", "updated_at": "", "gap": ""}
    if _is_unresolved(side):
        return {"status": "pending", "detail": "该侧待定", "updated_at": "", "gap": ""}
    if team is None:
        return {
            "status": "missing",
            "detail": "库内没有这支队",
            "updated_at": "",
            "gap": f"{side} 不在库内：没有身份、首发与画像",
        }
    info = starters.get(str(team["team_id"])) or {}
    count = int(info.get("starter_count") or 0)
    updated_at = str(info.get("updated_at") or "")
    if count <= 0:
        return {
            "status": "missing",
            "detail": "没有在职首发记录",
            "updated_at": "",
            "gap": f"{side} 没有在职首发记录",
        }
    age = _age_days(updated_at, now)
    if age is not None and age > LINEUP_STALE_DAYS:
        return {
            "status": "stale",
            "detail": f"{count} 人首发，{age} 天未更新",
            "updated_at": updated_at,
            "gap": f"{side} 首发 {age} 天未更新",
        }
    return {
        "status": "ok",
        "detail": f"{count} 人首发",
        "updated_at": updated_at,
        "gap": "",
    }


def _sub_status(*states: dict) -> str:
    order = {"missing": 3, "stale": 2, "ok": 1, "pending": 0}
    return max(states, key=lambda item: order.get(str(item.get("status")), 0)).get("status", "pending")


def _result_state(match: dict | None, match_time: str, game_format: str, now: datetime, match_unresolved: bool) -> dict:
    if match_unresolved:
        return {"status": "pending", "detail": "对阵未定", "recorded_at": "", "gap": ""}
    if match and str(match.get("status") or "") == "completed":
        return {
            "status": "ok",
            "detail": f"{match.get('winner')} 胜 {match.get('score_a')}:{match.get('score_b')}",
            "winner": str(match.get("winner") or ""),
            "score": f"{match.get('score_a')}:{match.get('score_b')}",
            "recorded_at": str(match.get("created_at") or ""),
            "gap": "",
        }
    hours = FORMAT_DURATION_HOURS.get(str(game_format or "").upper(), DEFAULT_DURATION_HOURS)
    started = _parse_dt(match_time)
    due = started + timedelta(hours=hours) if started else None
    if due is not None and now < due:
        return {"status": "pending", "detail": f"未到结果时刻（预计 {due.strftime('%m-%d %H:%M')} 后）", "recorded_at": "", "gap": ""}
    return {
        "status": "missing",
        "detail": "赛后仍未入库",
        "recorded_at": "",
        "gap": "比赛已过预计时长但结果仍未入库",
    }


def get_scope_overview() -> dict:
    try:
        leagues = get_current_event_scope_leagues()
        event = get_current_event()
    except (OSError, ValueError, TypeError) as exc:
        raise ScopeUnavailable("范围配置不可读") from exc
    now = _now()
    schedules = _scope_schedules(leagues)
    index = repository.team_index()
    names: list[str] = []
    for row in schedules:
        for side in (row.get("team_a"), row.get("team_b")):
            text = str(side or "").strip()
            if text and not _is_unresolved(text) and text not in names:
                names.append(text)
    team_ids = [str(index[name.casefold()]["team_id"]) for name in names if name.casefold() in index]
    starters = repository.latest_starters(team_ids)
    profiles = repository.profile_updates([str(index[name.casefold()]["name"]) for name in names if name.casefold() in index])
    teams = []
    for name in names:
        team = index.get(name.casefold())
        if team is None:
            teams.append(
                {
                    "name": name,
                    "team_id": "",
                    "region": "",
                    "in_library": False,
                    "profile_updated_at": "",
                    "profile_age_days": None,
                    "lineup_updated_at": "",
                    "source": "",
                    "verified": False,
                    "gap": "库内没有这支队",
                }
            )
            continue
        profile_at = profiles.get(str(team["name"]), "")
        info = starters.get(str(team["team_id"])) or {}
        kind = str(team.get("source_kind") or "").strip()
        retrieved = str(team.get("source_updated_at") or "").strip()
        source_label = f"{kind}@{retrieved[:10]}" if kind else ""
        teams.append(
            {
                "name": name,
                "team_id": str(team["team_id"]),
                "region": str(team["region"] or ""),
                "in_library": True,
                "profile_updated_at": profile_at,
                "profile_age_days": _age_days(profile_at, now),
                "lineup_updated_at": str(info.get("updated_at") or ""),
                "source": source_label,
                "verified": bool(str(team.get("verified_at") or "").strip()),
                "gap": "" if profile_at else "没有队伍画像",
            }
        )
    dates = sorted({str(row.get("date") or "") for row in schedules if row.get("date")})
    gaps = [f"{team['name']}：{team['gap']}" for team in teams if team["gap"]]
    return {
        "event": str(event.get("event") or ""),
        "leagues": leagues,
        "window": {"first_date": dates[0] if dates else "", "last_date": dates[-1] if dates else "", "match_count": len(schedules)},
        "teams": teams,
        "matches": [
            {
                "match_key": _match_key(row.get("source")),
                "date": str(row.get("date") or ""),
                "time": str(row.get("time_bjt") or ""),
                "label": f"{row.get('team_a')} vs {row.get('team_b')}",
                "format": str(row.get("format") or ""),
                "schedule_updated_at": str(row.get("updated_at") or ""),
            }
            for row in schedules
        ],
        "sources": [
            {"name": "英雄联盟数据库", "table": "schedules", "as_of": now.strftime("%Y-%m-%d %H:%M")},
            {"name": "current_event 范围配置", "as_of": now.strftime("%Y-%m-%d %H:%M")},
        ],
        "gaps": gaps,
        "settings": {"lineup_stale_days": LINEUP_STALE_DAYS, "profile_stale_days": PROFILE_STALE_DAYS},
    }


def get_coverage(date_value: str = "today", days: int = 1) -> dict:
    now = _now()
    start = _resolve_date(date_value, now)
    span = max(1, min(int(days or 1), 30))
    end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=span - 1)).strftime("%Y-%m-%d")
    try:
        leagues = get_current_event_scope_leagues()
    except (OSError, ValueError, TypeError) as exc:
        raise ScopeUnavailable("范围配置不可读") from exc
    schedules = _scope_schedules(leagues, start, end)
    index = repository.team_index()
    keys = [_match_key(row.get("source")) for row in schedules]
    matches = repository.list_matches_by_ids([key for key in keys if key])
    team_ids = [
        str(index[str(side).strip().casefold()]["team_id"])
        for row in schedules
        for side in (row.get("team_a"), row.get("team_b"))
        if str(side or "").strip().casefold() in index
    ]
    starters = repository.latest_starters(sorted(set(team_ids)))
    price_source = repository.has_price_source()
    prices = repository.latest_prices() if price_source else {}

    items = []
    all_gaps: list[str] = []
    for row in schedules:
        side_a = str(row.get("team_a") or "").strip()
        side_b = str(row.get("team_b") or "").strip()
        unresolved = _is_unresolved(side_a) or _is_unresolved(side_b) or side_a.casefold() == side_b.casefold()
        team_a = index.get(side_a.casefold()) if not unresolved else None
        team_b = index.get(side_b.casefold()) if not unresolved else None
        lineup_a = _lineup_state(side_a, team_a, starters, now, unresolved)
        lineup_b = _lineup_state(side_b, team_b, starters, now, unresolved)
        lineup_status = _sub_status(lineup_a, lineup_b)
        match = matches.get(_match_key(row.get("source")))
        result = _result_state(match, str(row.get("time_bjt") or ""), str(row.get("format") or ""), now, unresolved)
        quote = prices.get((side_a.casefold(), side_b.casefold())) if price_source else None
        if quote:
            price = {
                "status": "ok",
                "detail": f"{quote.get('price_a') or '-'} / {quote.get('price_b') or '-'}",
                "source": f"{quote.get('source_kind')}:{str(quote.get('source_ref') or '')[:24]}@{str(quote.get('recorded_at') or '')[:16]}",
                "recorded_at": str(quote.get("recorded_at") or ""),
                "gap": "",
            }
        elif price_source:
            price = {"status": "missing", "recorded_at": "", "gap": "这场还没有报价"}
        else:
            price = {"status": "missing", "recorded_at": "", "gap": "LOL 目前没有价格来源（未接入）"}
        gaps = [item for item in (lineup_a.get("gap"), lineup_b.get("gap"), price.get("gap"), result.get("gap")) if item]
        label = f"{side_a} vs {side_b}" if not unresolved else "对阵未定"
        all_gaps.extend([f"{label}：{gap}" for gap in gaps])
        items.append(
            {
                "match_key": _match_key(row.get("source")),
                "label": label,
                "date": str(row.get("date") or ""),
                "time": str(row.get("time_bjt") or ""),
                "stage": str(row.get("stage") or ""),
                "format": str(row.get("format") or ""),
                "lineup": {
                    "status": lineup_status,
                    "sides": {side_a or "A": lineup_a, side_b or "B": lineup_b},
                },
                "price": price,
                "result": result,
                "gaps": gaps,
            }
        )
    if not items:
        status = "empty"
        summary = f"{start} 起 {span} 天内范围里没有比赛"
    elif all_gaps:
        status = "partial"
        summary = f"{len(items)} 场比赛，{len(all_gaps)} 项缺口"
    else:
        status = "ok"
        summary = f"{len(items)} 场比赛，三项都没有洞"
    return {
        "status": status,
        "summary": summary,
        "date_from": start,
        "date_to": end,
        "event": str(get_current_event().get("event") or ""),
        "matches": items,
        "gap_count": len(all_gaps),
        "price_source_ready": price_source,
        "sources": [
            {"name": "英雄联盟数据库", "table": "schedules/matches/teams/rosters/team_profiles", "as_of": now.strftime("%Y-%m-%d %H:%M")},
        ],
    }


def _resolve_date(value: str, now: datetime) -> str:
    raw = str(value or "today").strip().lower()
    if raw in ("", "today", "今天"):
        return now.strftime("%Y-%m-%d")
    if raw in ("tomorrow", "明天"):
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if raw in ("yesterday", "昨天"):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return now.strftime("%Y-%m-%d")
