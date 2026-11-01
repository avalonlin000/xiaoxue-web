from __future__ import annotations

import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import history, naming

ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = ROOT / "config" / "football.json"
CACHE_PATH = ROOT / "data" / "football" / "matches.json"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
DEFAULT_LEAGUES = ("eng.1", "esp.1", "ita.1", "ger.1", "aus.1", "swe.1", "qat.1", "chn.1")
DEFAULT_WHITELIST = ("atalanta", "hammarby", "paderborn", "al sadd", "adelaide")
LEAGUE_NAMES = {
    "eng.1": "英超", "esp.1": "西甲", "ita.1": "意甲", "ger.1": "德甲", "fra.1": "法甲",
    "ned.1": "荷甲", "por.1": "葡超", "swe.1": "瑞典超", "nor.1": "挪超", "den.1": "丹超",
    "aus.1": "澳超", "qat.1": "卡塔尔联", "chn.1": "中超", "jpn.1": "J联赛", "kor.1": "K联赛",
    "usa.1": "美职联", "mex.1": "墨超", "bra.1": "巴甲", "arg.1": "阿甲", "tur.1": "土超",
    "ksa.1": "沙特联", "uae.1": "阿联酋联",
    "bel.1": "比甲", "sco.1": "苏超", "gre.1": "希超", "rus.1": "俄超",
    "uefa.champions": "欧冠", "uefa.europa": "欧联", "fifa.world": "世界杯",
}
SNAPSHOT_TTL_SECONDS = 300
CANDIDATE_BACK_HOURS = 4
CANDIDATE_AHEAD_HOURS = 36
FINISHED_KEEP_DAYS = 7
POOL_LINE = 2.5
EXCLUDE_LINE = 3.0

_refresh_lock = threading.Lock()


# ---------------------------------------------------------------- 基础

def _config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"leagues": list(DEFAULT_LEAGUES)}


def _get_json(url: str, timeout: int = 8) -> dict:
    request = Request(url, headers={"User-Agent": "xiaoxue-football/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _league_name(league: str) -> str:
    return LEAGUE_NAMES.get(league, league)


_TEAM_NAMES_PATH = ROOT / "config" / "football_teams_zh.json"
_team_names: dict[str, str] | None = None
_team_pattern: re.Pattern[str] | None = None


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def _load_team_names() -> dict[str, str]:
    global _team_names, _team_pattern
    if _team_names is None:
        try:
            payload = json.loads(_TEAM_NAMES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        raw = payload.get("teams") if isinstance(payload, dict) else {}
        raw = raw or {}
        _team_names = {_normalize_name(key): value for key, value in raw.items() if value}
        names = sorted((key for key, value in raw.items() if value), key=len, reverse=True)
        _team_pattern = re.compile("|".join(re.escape(name) for name in names), re.IGNORECASE) if names else None
    return _team_names or {}


def _team_names_table() -> dict[str, str]:
    return _load_team_names()


def _zh_team(name: str | None) -> str:
    """英文队名转中文：人工对照表优先，其次是自动翻译缓存，都没有才保留原名。"""
    original = str(name or "").strip()
    if not original:
        return "未知球队"
    table = _team_names_table()
    known = table.get(_normalize_name(original))
    if known:
        return known
    return naming.cached(original) or original


def _zh_text(value: str | None) -> str:
    """把句子里的英文队名换成中文。"""
    text = str(value or "")
    _load_team_names()
    if not text or _team_pattern is None:
        return text
    table = _team_names_table()
    return _team_pattern.sub(lambda match: table.get(_normalize_name(match.group(0)), match.group(0)), text)


_FIXTURE_RE = re.compile(r"([^（）()]+?) at ([^（）()]+?)(?=(?:\s\d+'+|\s*[）)]|$))")


def _localize_reason(text: str | None) -> str:
    """理由里的英文队名换中文，并把 'A at B' 按主场在前读成 'B vs A'。"""
    localized = _zh_text(text)
    return _FIXTURE_RE.sub(lambda m: f"{m.group(2).strip()} vs {m.group(1).strip()}", localized)


def _apply_team_names(rows: list[dict]) -> list[dict]:
    for row in rows:
        for side in ("home", "away"):
            team = row.get(side) or {}
            if team:
                team["display_name"] = _zh_team(team.get("name"))
        home = (row.get("home") or {}).get("display_name") or ""
        away = (row.get("away") or {}).get("display_name") or ""
        if home and away:
            row["display_name"] = f"{home} vs {away}"
        else:
            row["display_name"] = row.get("name") or "对阵待更新"
        for play in (row.get("plays") or {}).values():
            if not isinstance(play, dict) or not play.get("reasons"):
                continue
            play["reasons"] = [_localize_reason(reason) for reason in play["reasons"]]
    return rows


# ---------------------------------------------------------------- 快照

def _read_snapshot() -> dict:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"matches": [], "saved_at": None, "errors": [], "coverage": {}}
    if not isinstance(payload, dict):
        return {"matches": [], "saved_at": None, "errors": [], "coverage": {}}
    matches = payload.get("matches")
    return {
        "matches": matches if isinstance(matches, list) else [],
        "saved_at": payload.get("saved_at"),
        "errors": payload.get("errors") or [],
        "coverage": payload.get("coverage") or {},
    }


def _write_snapshot(matches: list[dict], errors: list[str], coverage: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "matches": matches,
        "errors": errors,
        "coverage": coverage,
        "saved_at": _now().isoformat(),
    }
    temporary = CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(CACHE_PATH)


def _snapshot_age(snapshot: dict) -> float:
    saved = _parse_time(snapshot.get("saved_at"))
    if not saved:
        return float("inf")
    return (_now() - saved).total_seconds()


# ---------------------------------------------------------------- 初盘

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
    home = (row.get("home") or {}).get("name", "")
    away = (row.get("away") or {}).get("name", "")
    text = f"{home} {away}".casefold()
    return any(name in text for name in names)


def _enrich_opening_total(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows

    def enrich(row: dict) -> dict:
        try:
            payload = _get_json(row["source_url"], timeout=6)
            total, market = _opening_total(payload)
            row["opening_total"] = total
            row["opening_market"] = market
        except Exception as exc:
            row["opening_total_error"] = str(exc)
        return row

    with ThreadPoolExecutor(max_workers=min(12, len(rows))) as executor:
        return list(executor.map(enrich, rows))


# ---------------------------------------------------------------- 赛程

def _dates() -> tuple[str, str]:
    now = _now()
    return now.strftime("%Y%m%d"), (now + timedelta(days=1)).strftime("%Y%m%d")


def _team(competitor: dict) -> dict:
    team = competitor.get("team") or {}
    return {
        "id": str(team.get("id") or ""),
        "name": team.get("displayName") or team.get("shortDisplayName") or "未知球队",
        "short_name": team.get("shortDisplayName") or team.get("displayName") or "未知球队",
        "home_away": competitor.get("homeAway") or "",
    }


def _normalize_event(event: dict, league: str) -> dict:
    competitions = event.get("competitions") or [{}]
    competitors = competitions[0].get("competitors", [])
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
        "league_name": _league_name(league),
        "name": event.get("name") or f"{home.get('name', '未知')} vs {away.get('name', '未知')}",
        "home": home,
        "away": away,
        "kickoff": event.get("date") or "",
        "status": status_type.get("state") or "unknown",
        "status_detail": status_type.get("detail") or (status.get("type") or {}).get("description") or "状态待更新",
        "opening_total": None,
        "opening_market": None,
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
        payload = _get_json(url, timeout=8)
        return [_normalize_event(event, league) for event in payload.get("events", [])], None
    except Exception as exc:  # 公开来源可取不到，保留可读缺口
        return [], f"{league}: {exc}"


# ---------------------------------------------------------------- 玩法

def _late_support(row: dict) -> dict:
    """75 分钟后大球：双方最近 5 场晚段资料给出保留 / 排除 / 待补。"""
    league = row.get("league") or ""
    profiles = []
    for team in ((row.get("home") or {}), (row.get("away") or {})):
        team_id = str(team.get("id") or "")
        profiles.append(history.profile(league, team_id) if team_id else {"matches": 0, "with_late": 0, "samples": [], "saved_at": None})
    readable = [item for item in profiles if item.get("matches")]
    if not readable:
        return {"decision": None, "readiness": "missing_late_history", "trigger": "missing_late_history",
                "reasons": ["近5场晚段进球资料未取得，先记待补"], "samples": []}
    best = max(int(item.get("with_late") or 0) for item in readable)
    samples: list[str] = []
    seen: set[str] = set()
    for item in readable:
        for sample in item.get("samples") or []:
            key = f"{sample.get('date')}|{sample.get('name')}"
            if key in seen:
                continue
            seen.add(key)
            samples.append(f"{sample.get('name') or '近期比赛'} {sample.get('clock') or ''} 有球".strip())
    distinct = {(s.get("date"), s.get("name")) for item in readable for s in (item.get("samples") or [])}
    reasons = [f"双方近5场共{len(distinct)}场在75分钟后有球"]
    reasons.extend(samples[:2])
    if best >= 2 or len(seen) >= 3:
        return {"decision": "keep", "readiness": "ready", "trigger": "late_support", "reasons": reasons, "samples": samples[:3]}
    if all(int(item.get("with_late") or 0) == 0 for item in readable):
        return {"decision": "exclude", "readiness": "ready", "trigger": "no_late_support",
                "reasons": ["双方最近5场都没有75分钟后进球"], "samples": []}
    return {"decision": None, "readiness": "thin_late_history", "trigger": "thin_late_history",
            "reasons": ["晚段样本不足，先记待补"], "samples": samples[:3]}


def _half_support(row: dict) -> list[str]:
    """半破支撑事实：双方近 5 场上半场有球的场次。"""
    league = row.get("league") or ""
    notes: list[str] = []
    for team in ((row.get("home") or {}), (row.get("away") or {})):
        team_id = str(team.get("id") or "")
        data = history.cached(league, team_id) if team_id else None
        if not data or not data.get("matches"):
            continue
        count = int(data.get("with_first_half") or 0)
        name = _zh_team(team.get("name") or team.get("short_name"))
        if not count:
            notes.append(f"{name}近{data['matches']}场无上半场进球")
            continue
        sample = (data.get("first_half_samples") or [{}])[0]
        tail = f"（{sample.get('name')} {sample.get('clock')} 有球）" if sample.get("name") else ""
        notes.append(f"{name}近{data['matches']}场有{count}场上半场进球{tail}")
    return notes


def _apply_play_rules(rows: list[dict], config: dict) -> list[dict]:
    for row in rows:
        row.setdefault("plays", {})
        total = row.get("opening_total")
        whitelisted = _is_whitelisted(row, config)
        if total is None:
            row["plays"]["half_break"] = {"decision": None, "readiness": "missing_opening_total",
                                          "trigger": "missing_opening_total", "reasons": ["真实初盘未取得，先记待补"]}
            row["plays"]["late_over"] = {"decision": None, "readiness": "missing_opening_total",
                                         "trigger": "missing_opening_total", "reasons": ["真实初盘未取得，先记待补"]}
            continue
        half_notes = _half_support(row)
        if total >= EXCLUDE_LINE:
            row["plays"]["half_break"] = {"decision": "exclude", "readiness": "ready", "trigger": "opening_total_3_plus",
                                          "reasons": [f"真实初盘{total:g}，3球或以上排除", *half_notes]}
        elif total >= POOL_LINE or whitelisted:
            reason = f"真实初盘{total:g}进入半破圈池" if total >= POOL_LINE else f"名单球队，初盘{total:g}进入半破圈池"
            reasons = [reason, *half_notes] if half_notes else [reason, "上半场进球样本待补"]
            row["plays"]["half_break"] = {"decision": "keep", "readiness": "ready", "trigger": "opening_pool", "reasons": reasons}
        else:
            row["plays"]["half_break"] = {"decision": None, "readiness": "outside_pool", "trigger": "opening_below_pool",
                                          "reasons": [f"真实初盘{total:g}低于2.5且未命中名单，不在半破圈池"]}
        if total >= POOL_LINE or whitelisted:
            row["plays"]["late_over"] = _late_support(row)
        else:
            row["plays"]["late_over"] = {"decision": "exclude", "readiness": "ready", "trigger": "opening_total_below_2_5",
                                         "reasons": [f"真实初盘{total:g}低于2.5且未命中名单"]}
    return rows


# ---------------------------------------------------------------- 刷新

def _translate_missing_names(rows: list[dict]) -> None:
    """新球队自动补中文名：查不到对照表的交给翻译模型，一次翻译长期有效。"""
    table = _team_names_table()
    missing = []
    for row in rows:
        for side in ("home", "away"):
            team = row.get(side) or {}
            name = str(team.get("name") or "").strip()
            if not name or _normalize_name(name) in table:
                continue
            if naming.cached(name):
                continue
            missing.append(name)
    if missing:
        try:
            naming.resolve(missing)
        except Exception:
            pass


def _prefetch_late_history(rows: list[dict], config: dict) -> None:
    """只给接下来会看的比赛预热晚段资料；超出窗口或不在圈池的不抓。"""
    now = _now()
    targets: list[tuple[str, str]] = []
    for row in rows:
        if row.get("status") in {"post", "completed"}:
            continue
        kickoff = _parse_time(row.get("kickoff"))
        if kickoff and kickoff > now + timedelta(hours=CANDIDATE_AHEAD_HOURS):
            continue
        total = row.get("opening_total")
        if total is None or (total < POOL_LINE and not _is_whitelisted(row, config)):
            continue
        for team in ((row.get("home") or {}), (row.get("away") or {})):
            team_id = str(team.get("id") or "")
            if team_id:
                targets.append((row.get("league") or "", team_id))
    history.prefetch(targets)


def _reuse_previous_late(previous: dict[str, dict], rows: list[dict]) -> None:
    """本轮没抓到晚段资料时，沿用上次已算出的结论，避免页面来回跳。"""
    for row in rows:
        old = (previous.get(row.get("id")) or {}).get("plays", {}).get("late_over") or {}
        new = row.get("plays", {}).get("late_over") or {}
        if new.get("decision") is None and old.get("decision"):
            row["plays"]["late_over"] = old


def _prune(rows: list[dict]) -> list[dict]:
    now = _now()
    keep = []
    for row in rows:
        home_id = str((row.get("home") or {}).get("id") or "")
        away_id = str((row.get("away") or {}).get("id") or "")
        if not home_id or not away_id:
            continue
        kickoff = _parse_time(row.get("kickoff"))
        if not kickoff:
            keep.append(row)
            continue
        finished = row.get("status") in {"post", "completed"}
        if finished:
            if (now - kickoff) <= timedelta(days=FINISHED_KEEP_DAYS):
                keep.append(row)
            continue
        if (now - kickoff) > timedelta(hours=24) or kickoff > now + timedelta(days=3):
            continue
        keep.append(row)
    return keep


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        seen[row.get("id") or ""] = row
    return list(seen.values())


def refresh() -> dict:
    """抓一轮赛程、初盘和晚段资料写成快照；失败保留上一份快照。"""
    if not _refresh_lock.acquire(blocking=False):
        return {"refreshed": False, "reason": "busy"}
    try:
        config = _config()
        leagues = tuple(config.get("leagues") or DEFAULT_LEAGUES)
        dates = _dates()
        errors: list[str] = []
        matches: list[dict] = []
        jobs = [(str(league), date) for league in leagues for date in dates]
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as executor:
            futures = [executor.submit(_matches_for, league, date) for league, date in jobs]
            for future in as_completed(futures):
                rows, error = future.result()
                matches.extend(rows)
                if error:
                    errors.append(error)
        matches = _dedupe(matches)
        matches = _enrich_opening_total(matches)
        previous = {row.get("id"): row for row in _prune(_read_snapshot()["matches"])}
        _translate_missing_names(matches)
        _prefetch_late_history(matches, config)
        matches = _apply_play_rules(matches, config)
        _reuse_previous_late(previous, matches)
        current = {row.get("id") for row in matches}
        merged = _prune(_dedupe(matches + [row for key, row in previous.items() if key not in current]))
        coverage = {"leagues": list(leagues), "source": "ESPN", "window_hours": CANDIDATE_AHEAD_HOURS}
        if merged:
            _write_snapshot(merged, errors, coverage)
        return {"refreshed": bool(merged), "matches": len(merged), "errors": errors}
    finally:
        _refresh_lock.release()


def _refresh_in_background() -> None:
    threading.Thread(target=refresh, name="football-refresh", daemon=True).start()


# ---------------------------------------------------------------- 读取

def _play_bucket(play: dict | None) -> str:
    play = play or {}
    decision = play.get("decision")
    if decision == "keep":
        return "keep"
    if decision == "exclude":
        return "exclude"
    if play.get("readiness") in {"outside_pool", "opening_below_pool"}:
        return "outside"
    return "pending"


def _in_view(row: dict, view: str, now: datetime) -> bool:
    kickoff = _parse_time(row.get("kickoff"))
    finished = row.get("status") in {"post", "completed"}
    if finished:
        if view != "all":
            return False
        return bool(kickoff) and (now - kickoff) <= timedelta(days=FINISHED_KEEP_DAYS)
    if kickoff and kickoff < now - timedelta(hours=CANDIDATE_BACK_HOURS):
        return False
    if kickoff and kickoff > now + timedelta(hours=CANDIDATE_AHEAD_HOURS):
        return False
    return True


def _sort_key(row: dict) -> tuple:
    status = row.get("status")
    kickoff = row.get("kickoff") or ""
    if status == "in":
        return (0, kickoff)
    if status in {"post", "completed"}:
        return (2, tuple(-ord(ch) for ch in kickoff[:19]))
    return (1, kickoff)


def list_matches(*, view: str = "candidates", play: str = "all", keyword: str = "") -> dict:
    now = _now()
    snapshot = _read_snapshot()
    stale = _snapshot_age(snapshot) > SNAPSHOT_TTL_SECONDS
    if not snapshot["matches"]:
        refresh()
        snapshot = _read_snapshot()
        stale = _snapshot_age(snapshot) > SNAPSHOT_TTL_SECONDS
    elif stale:
        _refresh_in_background()

    rows = [row for row in snapshot["matches"] if _in_view(row, view, now)]
    _apply_team_names(rows)
    for row in rows:
        row.setdefault("plays", {})
        row["league_name"] = _league_name(row.get("league") or "")

    # 默认观察清单只放真正可看的比赛：至少一种玩法已明确保留。
    # “全部比赛”保留核对和历史查看能力，不能被默认页混入待补或排除场次。
    if view == "candidates":
        rows = [row for row in rows if any(
            _play_bucket(row["plays"].get(key)) == "keep"
            for key in ("half_break", "late_over")
        )]

    counts = {
        "all": len(rows),
        "half_break": {"keep": 0, "pending": 0, "exclude": 0, "outside": 0},
        "late_over": {"keep": 0, "pending": 0, "exclude": 0, "outside": 0},
    }
    for row in rows:
        for key in ("half_break", "late_over"):
            counts[key][_play_bucket(row["plays"].get(key))] += 1

    needle = keyword.strip().lower()
    if needle:
        rows = [row for row in rows if needle in " ".join([
            str(row.get("name") or ""), str(row.get("display_name") or ""),
            str(row.get("league") or ""), str(row.get("league_name") or ""),
            str((row.get("home") or {}).get("name") or ""), str((row.get("home") or {}).get("display_name") or ""),
            str((row.get("away") or {}).get("name") or ""), str((row.get("away") or {}).get("display_name") or ""),
        ]).lower()]
    if view == "candidates" and play in {"half_break", "late_over"}:
        rows = [row for row in rows if _play_bucket(row["plays"].get(play)) == "keep"]
    rows.sort(key=_sort_key)
    errors = snapshot.get("errors") or []
    if rows and not errors:
        readiness = "ready"
    elif rows:
        readiness = "partial"
    else:
        readiness = "unavailable"
    return {
        "ok": not errors,
        "matches": rows,
        "counts": counts,
        "coverage": snapshot.get("coverage") or {"source": "ESPN"},
        "readiness": readiness,
        "stale": stale,
        "errors": errors,
        "updated_at": snapshot.get("saved_at") or _now().isoformat(),
    }


def get_match(match_id: str) -> dict:
    prefix, league, event_id = (match_id.split(":", 2) + ["", ""])[:3]
    if prefix != "espn" or not league or not event_id:
        raise ValueError("比赛身份无效")
    url = f"{ESPN_BASE}/{league}/summary?{urlencode({'event': event_id})}"
    payload = _get_json(url)
    competition = (payload.get("header", {}).get("competitions") or [{}])[0]
    competitors = competition.get("competitors", [])
    row = _normalize_event({"id": event_id, "date": competition.get("date") or "", "competitions": [{"competitors": competitors}], "status": competition.get("status", {})}, league)
    facts = []
    for item in payload.get("keyEvents", []) or []:
        if item.get("type", {}).get("text") == "Goal" or item.get("type", {}).get("id") == "goal":
            raw = _zh_text(item.get("text") or "")
            if raw.lower().startswith("goal"):
                score = raw.split(". ", 1)[0].replace("Goal! ", "").replace("Goal ", "").strip()
                parts = re.match(r"(.+?)\s(\d+)\s*,\s*(.+?)\s(\d+)$", score)
                if parts:
                    score = f"{parts.group(1)} {parts.group(2)}-{parts.group(4)} {parts.group(3)}"
                raw = f"进球 · {score}" if score else "进球"
            facts.append({"type": "goal", "text": raw or "进球事件", "clock": (item.get("clock") or {}).get("displayValue")})
    row["facts"] = facts
    cached = next((item for item in _read_snapshot()["matches"] if item.get("id") == match_id), None)
    if cached:
        row["opening_total"] = cached.get("opening_total")
        row["opening_market"] = cached.get("opening_market")
        row["plays"] = cached.get("plays") or row["plays"]
    _apply_team_names([row])
    row["summary_available"] = True
    row["summary_source"] = url
    row["raw_status"] = competition.get("status", {})
    return row
