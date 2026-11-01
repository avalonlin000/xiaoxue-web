"""球队近 5 场晚段（75 分钟后）进球资料。

只作为 75 分钟后玩法的支撑事实：读 ESPN 球队赛程 + 每场摘要里的进球时间，
按球队缓存到本地文件，避免每次刷新赛程都重复抓取。资料不足时返回空样本，
由上层判定“资料待补”，不把零样本当成没有进球。
"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
CACHE_PATH = ROOT / "data" / "football" / "team_history.json"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
SAMPLE_SIZE = 5
CACHE_HOURS = 24
LATE_MINUTE = 75
CACHE_VERSION = 2

_lock = threading.Lock()
_memory: dict[str, dict] | None = None


def _get_json(url: str, timeout: int = 8) -> dict:
    request = Request(url, headers={"User-Agent": "xiaoxue-football/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _load() -> dict[str, dict]:
    global _memory
    if _memory is not None:
        return _memory
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        _memory = payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        _memory = {}
    return _memory


def _save() -> None:
    if _memory is None:
        return
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(_memory, ensure_ascii=False), encoding="utf-8")
        temporary.replace(CACHE_PATH)
    except OSError:
        pass


def _minute(clock: str | None) -> int | None:
    match = re.match(r"(\d+)", str(clock or ""))
    return int(match.group(1)) if match else None


def _completed(events: list[dict], now: datetime) -> list[dict]:
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        state = ((competition.get("status") or {}).get("type") or {}).get("state") \
            or ((event.get("status") or {}).get("type") or {}).get("state") or ""
        date = event.get("date") or ""
        if state != "post" or not date:
            continue
        rows.append({"id": str(event.get("id") or ""), "date": date, "name": event.get("name") or "", "state": state})
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows[:SAMPLE_SIZE]


def _goal_marks(league: str, event_id: str) -> tuple[list[int], list[str], bool]:
    """返回 (进球分钟列表, 展示用时间, 资料是否可读取)。"""
    if not event_id:
        return [], [], False
    url = f"{ESPN_BASE}/{league}/summary?event={event_id}"
    try:
        payload = _get_json(url)
    except Exception:
        return [], [], False
    events = payload.get("keyEvents")
    if events is None:
        return [], [], False
    minutes: list[int] = []
    clocks: list[str] = []
    for item in events:
        kind = ((item.get("type") or {}).get("text") or "").lower()
        if "goal" not in kind:
            continue
        clock = (item.get("clock") or {}).get("displayValue") or ""
        minute = _minute(clock)
        if minute is None:
            continue
        minutes.append(minute)
        clocks.append(clock)
    return minutes, clocks, True


def _empty() -> dict:
    return {"matches": 0, "with_late": 0, "samples": [], "with_first_half": 0,
            "first_half_samples": [], "saved_at": None, "version": CACHE_VERSION}


def profile(league: str, team_id: str) -> dict:
    """某队最近 5 场：晚段（75+）与上半场进球资料。"""
    key = f"{league}:{team_id}"
    if not league or not team_id:
        return _empty()
    cache = _load()
    cached = cache.get(key)
    if cached and cached.get("saved_at") and cached.get("version") == CACHE_VERSION:
        try:
            saved = datetime.fromisoformat(cached["saved_at"])
            if datetime.now(timezone.utc) - saved < timedelta(hours=CACHE_HOURS):
                return cached
        except ValueError:
            pass
    now = datetime.now(timezone.utc)
    try:
        schedule = _get_json(f"{ESPN_BASE}/{league}/teams/{team_id}/schedule")
    except Exception:
        return cached if cached and cached.get("version") == CACHE_VERSION else _empty()
    events = _completed(schedule.get("events") or [], now)
    late_samples = []
    first_half_samples = []
    readable = 0
    with ThreadPoolExecutor(max_workers=min(SAMPLE_SIZE, max(1, len(events)))) as executor:
        results = list(executor.map(lambda event: _goal_marks(league, event["id"]), events))
    for event, (minutes, clocks, ok) in zip(events, results):
        if not ok:
            continue
        readable += 1
        label = {"date": (event["date"] or "")[:10], "name": event["name"]}
        late = [(minute, clock) for minute, clock in zip(minutes, clocks) if minute >= LATE_MINUTE]
        early = [(minute, clock) for minute, clock in zip(minutes, clocks) if minute <= 45]
        if late:
            late_samples.append(dict(label, clock=late[0][1]))
        if early:
            first_half_samples.append(dict(label, clock=early[0][1]))
    if not readable:
        return cached if cached and cached.get("version") == CACHE_VERSION else _empty()
    row = {
        "matches": readable,
        "with_late": len(late_samples),
        "samples": late_samples[:3],
        "with_first_half": len(first_half_samples),
        "first_half_samples": first_half_samples[:3],
        "saved_at": now.isoformat(),
        "version": CACHE_VERSION,
    }
    with _lock:
        cache[key] = row
        _save()
    return row


def cached(league: str, team_id: str) -> dict | None:
    """只读缓存，不触发网络请求。"""
    row = _load().get(f"{league}:{team_id}")
    if not row or row.get("version") != CACHE_VERSION:
        return None
    return row


def prefetch(targets: list[tuple[str, str]]) -> None:
    """批量预热，用于赛程刷新时的后台补资料。"""
    unique = {(league, str(team_id)) for league, team_id in targets if league and team_id}
    if not unique:
        return
    with ThreadPoolExecutor(max_workers=min(16, len(unique))) as executor:
        list(executor.map(lambda item: profile(*item), unique))
