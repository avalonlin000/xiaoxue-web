"""Configured schedule window and kickoff parsing shared by readers and workers."""
from datetime import datetime
from zoneinfo import ZoneInfo


ZONE = ZoneInfo("Asia/Shanghai")


def match_event(event: str, match_date: str, config: dict) -> str:
    """Resolve current-event aliases for upcoming preparation, not stored records.

    Past snapshots keep their identity. Multiple configured source stages are
    not interchangeable, so an ambiguous configuration must not merge them.
    """
    if match_date < datetime.now(ZONE).date().isoformat():
        return event
    leagues = list(dict.fromkeys(value for value in config.get("leagues", []) if value))
    if len(leagues) > 1:
        return event
    canonical = leagues[0] if leagues else config.get("event")
    names = [config.get("event"), *config.get("aliases", []), *leagues]
    normalize = lambda value: " ".join(str(value or "").casefold().split())
    return canonical if canonical and normalize(event) in {normalize(name) for name in names if name} else event


def window_days(config: dict) -> int:
    value = (config.get("preparation") or {}).get("upcoming_days", 7)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 14:
        raise ValueError("近期准备范围应为1至14天")
    return value


def kickoff(match: dict) -> datetime:
    raw = str(match.get("time") or match.get("match_time") or "").strip()
    if not raw:
        raise ValueError("开赛时间尚未明确")
    day = match.get("date") or match.get("match_date") or ""
    stamp = raw if len(raw) > 10 and raw[4:5] == "-" else f"{day}T{raw}"
    value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (value.replace(tzinfo=ZONE) if value.tzinfo is None else value).astimezone(ZONE)


def schedules(fetch, config: dict, start: str, end: str, limit: int = 200) -> tuple[list[dict], bool]:
    """Filter the canonical stage before LIMIT; retain an explicit overflow flag."""
    scopes = config.get("leagues") or [config.get("event") or ""]
    rows, overflow = {}, False
    for scope in dict.fromkeys(scopes):
        page = fetch({"date_from": start, "date_to": end, "event": scope}, limit + 1)
        overflow |= len(page) > limit
        for row in page:
            key = tuple(str(row.get(field) or "") for field in ("date", "time", "team_a", "team_b", "stage"))
            rows[key] = row
    ordered = [row for _, row in sorted(rows.items())]
    return ordered[:limit], overflow or len(ordered) > limit
