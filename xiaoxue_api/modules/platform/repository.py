from __future__ import annotations

from datetime import datetime
import json
import os
import shutil

from xiaoxue_api.core.database import DB_PATH, db


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
WIKI_DIR = os.environ.get("XIAOXUE_WIKI_DIR", "/home/ubuntu/workspace/knowledge/wiki")
TK_DIR = os.path.join(WIKI_DIR, "小雪电竞", "原始资料", "tk")
SKILL_DIR_XIAOBAI = os.environ.get("XIAOXUE_SKILL_DIR_XIAOBAI", "/home/ubuntu/.hermes/profiles/xiaobai/skills")
SKILL_DIR_MAIN = os.environ.get("XIAOXUE_SKILL_DIR_MAIN", "/home/ubuntu/.hermes/skills")


def collect_checks() -> dict:
    checks = {}
    try:
        with db() as conn:
            team_count = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
            schedule_count = conn.execute("SELECT COUNT(*) AS n FROM schedules").fetchone()["n"]
        checks["database"] = {"ok": True, "path": DB_PATH, "teams": team_count, "schedules": schedule_count}
    except Exception as exc:
        checks["database"] = {"ok": False, "path": DB_PATH, "error": str(exc)}
    dist_index = os.path.join(ROOT, "dist", "index.html")
    memory_bank = os.path.join(ROOT, "memory-bank")
    checks["dist"] = {"ok": os.path.exists(dist_index), "path": dist_index}
    checks["tk_dir"] = {"ok": os.path.isdir(TK_DIR), "path": TK_DIR}
    checks["skill_dirs"] = {
        "ok": os.path.isdir(SKILL_DIR_XIAOBAI) or os.path.isdir(SKILL_DIR_MAIN),
        "xiaobai": os.path.isdir(SKILL_DIR_XIAOBAI), "main": os.path.isdir(SKILL_DIR_MAIN),
    }
    checks["memory_bank"] = {
        "ok": all(os.path.exists(os.path.join(memory_bank, name)) for name in ("README.md", "modules.md", "progress.md")),
        "path": memory_bank, "files": ["README.md", "modules.md", "progress.md"],
    }
    checks["data_readiness"] = readiness_check()
    total, used, free = shutil.disk_usage("/")
    used_pct = round(used / total * 100, 1)
    checks["disk"] = {
        "ok": used_pct < 92, "warn": used_pct >= 85, "used_percent": used_pct,
        "free_gb": round(free / (1024 ** 3), 1),
    }
    return checks


def readiness_check() -> dict:
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    path = os.path.join(os.environ.get("XIAOXUE_READINESS_ROOT", "/home/ubuntu/lol_data/scripts"), f"data_readiness_manifest_{date}.json")
    due = readiness_due(now)
    try:
        with open(path, encoding="utf-8") as source:
            readiness = json.load(source)
    except (OSError, json.JSONDecodeError):
        readiness = None
    stages = {
        str(item.get("id")): item for item in ((readiness or {}).get("stages") or []) if isinstance(item, dict)
    }
    def stage_ok(stage_id):
        stage = stages.get(stage_id) or {}
        try:
            return stage.get("status") == "ok" and int(stage.get("exit_code", 1)) == 0
        except (TypeError, ValueError):
            return False
    ok = bool(
        isinstance(readiness, dict) and readiness.get("schema") == "xiaoxue-data-readiness-run-v1"
        and str(readiness.get("created_at") or "")[:10] == date and readiness.get("ok") is True
        and readiness.get("mode") == "full" and all(stage_ok(item) for item in ("scoregg_refresh", "ts_update"))
    )
    if ok:
        status, state = "ready", "ready"
    elif isinstance(readiness, dict) and readiness.get("mode") == "check-only":
        status, state = "diagnostic_only", "failed"
    elif readiness is None and now < due:
        # The daily pipeline runs at 05:30; before its scheduled slot there is
        # nothing to read yet, which is a normal wait rather than a fault.
        status, state = "not_due", "not_due"
    else:
        status, state = "missing_or_blocked", "failed"
    message = readiness_message(status, due)
    return {"ok": ok, "path": path, "status": status, "state": state, "due_at": due.isoformat(timespec="minutes"), "message": message}


def readiness_due(now: datetime) -> datetime:
    """Scheduled slot of the daily data pipeline; later than this counts as a fault."""
    raw = os.environ.get("XIAOXUE_READINESS_DUE", "05:45")
    try:
        hour, minute = (int(part) for part in str(raw).split(":", 1))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (TypeError, ValueError):
        return now.replace(hour=5, minute=45, second=0, microsecond=0)


def readiness_message(status: str, due: datetime) -> str:
    if status == "ready":
        return ""
    if status == "not_due":
        return f"今日数据尚未生成：每天 05:30 自动刷新，{due:%H:%M} 前属正常等待"
    if status == "diagnostic_only":
        return "今日数据只做过检查模式，没有正式刷新结果"
    return "今日数据没有生成或未通过检查，需要重新刷新"


def index_path() -> str:
    dist = os.path.join(ROOT, "dist", "index.html")
    return dist if os.path.exists(dist) else os.path.join(ROOT, "index.html")
