from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "football.json"
CACHE_PATH = ROOT / "data" / "football" / "matches.json"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
DEFAULT_LEAGUES = ("eng.1", "esp.1", "ita.1", "ger.1", "aus.1", "swe.1", "qat.1", "chn.1")
DEFAULT_WHITELIST = ("atalanta", "hammarby", "paderborn", "al sadd", "adelaide")


def _config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"leagues": list(DEFAULT_LEAGUES)}


def _get_json(url: str, timeout: int = 8) -> dict:
    request = Request(url, headers={"User-Agent": "xiaoxue-football/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _opening_total(payload: dict) -> tuple[float | None, dict | None]:
    for odds in payload.get("odds", []) or []:
        total = odds.get("total") or {}
        over = total.get("over") or {}
        opening = over.get("open") or {}
        line = str(opening.get("line") or "").lower().lstrip("ou")
        try:
            return float(line), {"provider": (odds.get("provider") or {}).get("name", ""), "line": line, "odds": opening.get("odds")}
        except (TypeError, ValueError):
            continue
    return None, None


def _is_whitelisted(row: dict, config: dict) -> bool:
    names = tuple(str(item).casefold() for item in config.get("whitelist", DEFAULT_WHITELIST))
    return any(name in f"{row['home']['name']} {row['away']['name']}".casefold() for name in names)


def _enrich_opening_total(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    config = _config()
    def enrich(row: dict) -> dict:
        try:
            payload = _get_json(row["source_url"])
            total, market = _opening_total(payload)
            row["opening_total"] = total
            row["opening_market"] = market
            circle = total is not None and (total >= 2.5 or _is_whitelisted(row, config))
            if total is not None and total >= 3:
                row["plays"]["half_break"] = {"decision": "exclude", "readiness": "ready", "trigger": "opening_total_3_plus", "reasons": ["真实初盘3球或以上"]}
            elif circle:
                row["plays"]["half_break"] = {"decision": "keep", "readiness": "ready", "trigger": "opening_pool", "reasons": [f"真实初盘{total:g}进入半破圈池"]}
            if total is not None and total < 2.5 and not _is_whitelisted(row, config):
                row["plays"]["late_over"] = {"decision": "exclude", "readiness": "ready", "trigger": "opening_total_below_2_5", "reasons": ["真实初盘低于2.5且未命中名单"]}
            elif circle:
                row["plays"]["late_over"] = {"decision": None, "readiness": "missing_late_history", "reasons": ["初盘进入圈池，等待近5场晚段进失球资料"]}
        except Exception as exc:
            row["opening_total_error"] = str(exc)
        return row
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as executor:
        rows = list(executor.map(enrich, rows))
    return rows


def _dates() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d"), (now + timedelta(days=1)).strftime("%Y%m%d")


def _read_cache() -> list[dict]:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return payload.get("matches", []) if isinstance(payload, dict) else []
    except (OSError, ValueError):
        return []


def _write_cache(matches: list[dict]) -> None:
    if not matches:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps({"matches": matches, "saved_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(CACHE_PATH)


def _team(competitor: dict) -> dict:
    team = competitor.get("team") or {}
    return {
        "id": str(team.get("id") or ""),
        "name": team.get("displayName") or team.get("shortDisplayName") or "未知球队",
        "short_name": team.get("shortDisplayName") or team.get("displayName") or "未知球队",
        "home_away": competitor.get("homeAway") or "",
    }


def _normalize_event(event: dict, league: str) -> dict:
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    home = next((_team(item) for item in competitors if item.get("homeAway") == "home"), {})
    away = next((_team(item) for item in competitors if item.get("homeAway") == "away"), {})
    status = event.get("status") or {}
    status_type = status.get("type") or {}
    event_id = str(event.get("id") or "")
    return {
        "id": f"espn:{league}:{event_id}",
        "source_id": event_id,
        "source": "ESPN",
        "league": league,
        "league_name": (event.get("season") or {}).get("displayName") or league,
        "name": event.get("name") or f"{home.get('name', '未知')} vs {away.get('name', '未知')}",
        "home": home,
        "away": away,
        "kickoff": event.get("date") or "",
        "status": status_type.get("state") or "unknown",
        "status_detail": status_type.get("detail") or status.get("type", {}).get("description") or "状态待更新",
        "opening_total": None,
        "plays": {
            "half_break": {"decision": None, "readiness": "missing_opening_total", "reasons": []},
            "late_over": {"decision": None, "readiness": "missing_opening_total", "reasons": []},
        },
        "facts": [],
        "source_url": f"{ESPN_BASE}/{league}/summary?event={event_id}",
    }


def _matches_for(league: str, date: str) -> tuple[list[dict], str | None]:
    query = urlencode({"dates": date})
    url = f"{ESPN_BASE}/{league}/scoreboard?{query}"
    try:
        payload = _get_json(url)
        return [_normalize_event(event, league) for event in payload.get("events", [])], None
    except Exception as exc:  # public sources are optional; preserve a readable gap
        return [], f"{league}: {exc}"


def list_matches(*, view: str = "candidates", play: str = "all", keyword: str = "") -> dict:
    config = _config()
    leagues = tuple(config.get("leagues") or DEFAULT_LEAGUES)
    dates = _dates()
    matches: list[dict] = []
    errors: list[str] = []
    jobs = [(str(league), date) for league in leagues for date in dates]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as executor:
        futures = [executor.submit(_matches_for, league, date) for league, date in jobs]
        for future in as_completed(futures):
            rows, error = future.result()
            matches.extend(rows)
            if error:
                errors.append(error)
    matches = _enrich_opening_total(matches)
    cached = _read_cache()
    if matches:
        known = {row.get("id") for row in matches}
        matches.extend(row for row in cached if row.get("id") not in known)
        _write_cache(matches)
    elif cached:
        matches = cached
    needle = keyword.strip().lower()
    if needle:
        matches = [
            row for row in matches
            if needle in row["name"].lower() or needle in row["league"].lower()
            or needle in row["home"]["name"].lower() or needle in row["away"]["name"].lower()
        ]
    if play in {"half_break", "late_over"}:
        matches = [row for row in matches if play in row["plays"]]
    if view == "candidates":
        # Missing opening totals are deliberately visible as pending, not discarded.
        matches = [row for row in matches if row["status"] not in {"post", "completed"}]
    matches.sort(key=lambda row: (row["kickoff"] or "9999", row["name"]))
    return {
        "ok": not errors,
        "matches": matches,
        "coverage": {"leagues": list(leagues), "window_hours": 24, "source": "ESPN"},
        "readiness": "ready" if matches and not errors else ("partial" if matches else "unavailable"),
        "errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_match(match_id: str) -> dict:
    prefix, league, event_id = (match_id.split(":", 2) + [""])[:3]
    if prefix != "espn" or not league or not event_id:
        raise ValueError("比赛身份无效")
    url = f"{ESPN_BASE}/{league}/summary?{urlencode({'event': event_id})}"
    payload = _get_json(url)
    event = payload.get("header", {}).get("competitions", [{}])[0]
    competitors = event.get("competitors", [])
    row = _normalize_event({"id": event_id, "date": payload.get("header", {}).get("season", {}).get("year"), "competitions": [{"competitors": competitors}], "status": event.get("status", {})}, league)
    facts = []
    for item in payload.get("keyEvents", []) or []:
        if item.get("type", {}).get("text") == "Goal" or item.get("type", {}).get("id") == "goal":
            facts.append({"type": "goal", "text": item.get("text") or "进球事件", "clock": item.get("clock", {}).get("displayValue")})
    row["facts"] = facts
    row["summary_available"] = True
    row["summary_source"] = url
    row["raw_status"] = payload.get("header", {}).get("competitions", [{}])[0].get("status", {})
    return row
