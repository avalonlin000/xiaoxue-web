"""本场事实：赛程、赛制、本届战绩、双方近期赛果与官方名册。

数据来自 Riot 官方赛事接口（公开 key），不消耗搜索配额；接口不可用时
返回 limitation，不阻断其他阶段，也不编造任何缺失项。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

API = "https://esports-api.lolesports.com/persisted/gw/"
KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
CACHE_TTL = 600
CACHE_VERSION = 1

EVENT_ALIASES = {
    "worlds": {"s16全球总决赛", "s16 世界赛", "s16世界赛", "worlds 2026", "2026 world championship", "worlds"},
    "msi": {"msi", "季中冠军赛"},
}
ACADEMY_MARKERS = ("academy", "challengers", "youth", "junior", "二队", "青训")


def _cache_dir() -> Path:
    root = Path(os.environ.get("XIAOXUE_COLLECTION_DIR", str(Path(__file__).resolve().parents[3] / "data" / "current_event_materials")))
    path = root / ".facts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cached(key: str):
    path = _cache_dir() / f"{key}.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if payload.get("version") != CACHE_VERSION or time.time() - payload.get("at", 0) > CACHE_TTL:
        return None
    return payload.get("data")


def _store(key: str, data) -> None:
    path = _cache_dir() / f"{key}.json"
    try:
        path.write_text(json.dumps({"version": CACHE_VERSION, "at": time.time(), "data": data}, ensure_ascii=False))
    except OSError:
        pass


def _get(path: str, timeout: float = 12):
    key = "api_" + str(abs(hash(path)))
    hit = _cached(key)
    if hit is not None:
        return hit
    request = urllib.request.Request(API + path, headers={"x-api-key": KEY, "User-Agent": "XiaoxueWorkbench/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    _store(key, data)
    return data


def _bjt(stamp: str) -> str:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8)))
    return moment.strftime("%m-%d %H:%M")


def _league_slug(event: str) -> str:
    text = " ".join(str(event or "").casefold().split())
    for slug, names in EVENT_ALIASES.items():
        if text in names or any(name in text for name in names if len(name) > 3):
            return slug
    return ""


def _tournament(league_slug: str, match_date: str) -> tuple[str, str]:
    leagues = _get("getLeagues?hl=zh-CN").get("data", {}).get("leagues", [])
    league = next((row for row in leagues if row.get("slug") == league_slug), None)
    if not league:
        raise ValueError("未找到对应赛事")
    tournaments = (_get(f"getTournamentsForLeague?hl=zh-CN&leagueId={league['id']}")
                   .get("data", {}).get("leagues", [{}])[0].get("tournaments", []))
    for row in tournaments:
        if row.get("startDate", "") <= match_date <= row.get("endDate", ""):
            return league["id"], row["id"]
    raise ValueError("当前赛季赛程尚未发布")


def _roster(team: str) -> list[str]:
    teams = _get("getTeams?hl=zh-CN").get("data", {}).get("teams", [])
    options = [row for row in teams
               if team.upper() in {str(row.get("code") or "").upper(), str(row.get("slug") or "").upper(),
                                   str(row.get("name") or "").upper()}]
    preferred = [row for row in options
                 if not any(marker in str(row.get("name") or "").casefold() for marker in ACADEMY_MARKERS)] or options
    if not preferred:
        return []
    players = preferred[0].get("players") or []
    roles = {"top": "上单", "jungle": "打野", "mid": "中单", "bottom": "ADC", "support": "辅助"}
    return [f"{roles.get(p.get('role'), p.get('role') or '')} {p.get('summonerName') or p.get('firstName') or ''}".strip()
            for p in players if p.get("role") in roles and (p.get("summonerName") or p.get("firstName"))]


def facts(identity: dict) -> tuple[list[dict], list[str]]:
    """Return one deterministic facts section plus limitations."""
    team_a, team_b = str(identity.get("team_a") or "").upper(), str(identity.get("team_b") or "").upper()
    match_date = str(identity.get("match_date") or "")
    if not team_a or not team_b or not match_date or "TBD" in {team_a, team_b}:
        return [], []
    slug = _league_slug(str(identity.get("event") or ""))
    if not slug:
        return [], ["本场事实：赛事不在官方接口映射内，未生成赛程与战绩区块"]
    try:
        league_id, _ = _tournament(slug, match_date)
        events = (_get(f"getSchedule?hl=zh-CN&leagueId={league_id}")
                  .get("data", {}).get("schedule", {}).get("events", []))
    except Exception:
        return [], ["本场事实：官方赛事接口暂不可读，赛程与战绩未生成"]
    window_start = (datetime.fromisoformat(match_date) - timedelta(days=40)).strftime("%Y-%m-%d")
    window_end = (datetime.fromisoformat(match_date) + timedelta(days=2)).strftime("%Y-%m-%d")
    rows = []
    for event in events:
        stamp = event.get("startTime") or ""
        if not (window_start <= stamp[:10] <= window_end):
            continue
        match = event.get("match") or {}
        sides = match.get("teams") or []
        if len(sides) != 2:
            continue
        codes = [str(side.get("code") or "").upper() for side in sides]
        rows.append({"stamp": stamp, "state": event.get("state"), "stage": event.get("blockName") or "",
                     "codes": codes, "teams": sides, "bo": (match.get("strategy") or {}).get("count")})
    target = next((row for row in rows if set(row["codes"]) == {team_a, team_b}
                   and _bjt(row["stamp"])[:5] == match_date[5:]), None)
    items = []
    if target:
        sides = target["teams"]
        records = [(side.get("record") or {}) for side in sides]
        start = _bjt(target["stamp"])
        format_note = f"BO{target['bo']}" if target.get("bo") else "赛制待确认"
        record_note = "、".join(
            f"{code} 本届 {record.get('wins')}-{record.get('losses')}"
            for code, record in zip(target["codes"], records) if record.get("wins") is not None
        )
        items.append({"text": f"{start}（北京时间）{target['stage']} {team_a} vs {team_b}，{format_note}。" + (f"{record_note}。" if record_note else ""),
                      "source": "Riot 官方赛事接口", "verification": "official_api",
                      "url": "https://lolesports.com/schedule"})
    for team in (team_a, team_b):
        played = [row for row in rows if team in row["codes"] and row["state"] == "completed"]
        played.sort(key=lambda row: row["stamp"], reverse=True)
        if not played:
            continue
        lines = []
        for row in played[:3]:
            index = row["codes"].index(team)
            own, other = row["teams"][index], row["teams"][1 - index]
            own_wins = (own.get("result") or {}).get("gameWins")
            other_wins = (other.get("result") or {}).get("gameWins")
            score = f"{own_wins}:{other_wins}" if own_wins is not None and other_wins is not None else "比分未知"
            lines.append(f"{_bjt(row['stamp'])} {row['stage']} {score} {row['codes'][1 - index]}")
        items.append({"text": f"{team} 本届最近赛果：" + "；".join(lines), "source": "Riot 官方赛事接口",
                      "verification": "official_api", "url": "https://lolesports.com/schedule"})
    h2h = [row for row in rows if set(row["codes"]) == {team_a, team_b} and row["state"] == "completed"]
    if h2h:
        lines = []
        for row in sorted(h2h, key=lambda row: row["stamp"], reverse=True)[:2]:
            a_wins = (row["teams"][row["codes"].index(team_a)].get("result") or {}).get("gameWins")
            b_wins = (row["teams"][row["codes"].index(team_b)].get("result") or {}).get("gameWins")
            lines.append(f"{_bjt(row['stamp'])} {team_a} {a_wins}:{b_wins} {team_b}")
        items.append({"text": "本届交手：" + "；".join(lines), "source": "Riot 官方赛事接口",
                      "verification": "official_api", "url": "https://lolesports.com/schedule"})
    for team in (team_a, team_b):
        try:
            players = _roster(team)
        except Exception:
            players = []
        if players:
            items.append({"text": f"{team} 官方登记名单（含替补/青训，不代表本场首发）：" + "、".join(players),
                          "source": "Riot 官方赛事接口", "verification": "official_api",
                          "url": "https://lolesports.com/schedule"})
    if not items:
        return [], ["本场事实：官方接口未返回该场比赛，赛程与战绩未生成"]
    return [{"id": "facts", "title": "本场事实", "items": items}], []
