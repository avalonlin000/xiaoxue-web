from __future__ import annotations

import re
from datetime import datetime

from workflow_contracts import build_daily_content_files
from xiaoxue_api.modules.team_data.public import list_schedules

from . import repository


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MATCH_CONTENT_KINDS = {"daily_report", "pre_match_card", "trading_report"}


class ConfigurationUnavailable(RuntimeError):
    pass


def get_operating_state() -> dict:
    try:
        daily = repository.load_config().get("daily_content") or {}
    except (OSError, ValueError, TypeError):
        return {"state": "unknown", "message": "日报运行状态配置不可用"}
    return {
        "state": daily.get("operating_state", "active"),
        "message": daily.get("operating_message", ""),
    }


def resolve_date(value: str | None) -> str:
    raw = (value or "today").strip().lower()
    if raw == "today":
        return datetime.now().strftime("%Y-%m-%d")
    if not DATE_RE.fullmatch(raw):
        raise ValueError("非法 date 参数；只支持 today 或 YYYY-MM-DD")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("非法 date 参数；只支持 today 或 YYYY-MM-DD") from exc
    return raw


def get_daily_content(date: str = "today") -> dict:
    date_str = resolve_date(date)
    try:
        config = repository.load_config()
        files = build_daily_content_files(config, date_str)
    except (OSError, ValueError) as exc:
        raise ConfigurationUnavailable(f"每日准备模块配置不可用：{exc}") from exc
    matches = list_schedules({"date_from": date_str, "date_to": date_str}, 12)
    items = []
    for key, meta in files.items():
        artifact = repository.read_artifact(meta["path"])
        items.append({
            "id": key,
            "title": meta["title"],
            "kind": meta["kind"],
            "path": meta["path"],
            "exists": artifact["exists"],
            "updated_at": datetime.fromtimestamp(artifact["updated_at"]).isoformat(timespec="seconds")
            if artifact["updated_at"] else None,
            "size_bytes": artifact["size_bytes"],
            "summary": summarize(artifact["content"]),
        })
    required = [item for item in items if item["kind"] in MATCH_CONTENT_KINDS]
    day_state = "no_matches" if not matches else (
        "content_missing" if any(not item["exists"] for item in required) else "ready"
    )
    return {
        "ok": True, "date": date_str, "source": "local_whitelist",
        "day_state": day_state, "match_count": len(matches), "matches": matches, "items": items,
    }


def summarize(text: str, max_chars: int = 180) -> str:
    if not text:
        return ""
    lines, in_frontmatter = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not line:
            continue
        lines.append(line.lstrip("#").strip() if line.startswith("#") else line)
        if len(" ".join(lines)) >= max_chars:
            break
    summary = " ".join(lines).strip()
    return summary[:max_chars].rstrip() + "…" if len(summary) > max_chars else summary
