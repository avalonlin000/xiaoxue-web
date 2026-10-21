from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

from xiaoxue_api.core.health_projection import project_module_health
from xiaoxue_api.modules.daily_content.public import get_operating_state

from . import repository


_boot_status = {}
DATA_ROOT = Path("/home/ubuntu/lol_data")
DATA_REFRESH_PIPELINE = DATA_ROOT / "scripts" / "data_readiness_pipeline.py"


def configure_boot_status(status: dict) -> None:
    global _boot_status
    _boot_status = dict(status)


def health() -> dict:
    checks = repository.collect_checks()
    checks["daily_operation"] = get_operating_state()
    module_health = project_module_health(checks, _boot_status)
    return {
        "ok": all(_check_passed(item) for item in checks.values()),
        "status": module_health["status"],
        "modules": module_health["modules"],
        "capabilities": module_health["capabilities"],
        "service": "xiaoxue-workbench-api", "time": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
    }


def _check_passed(value) -> bool:
    """A dependency that is not produced yet is a wait, not an outage."""
    if isinstance(value, dict):
        if "ok" not in value:
            return True
        return bool(value.get("ok")) or value.get("state") == "not_due"
    return bool(value)


def links(team: str = "") -> dict:
    # 8768 legacy RAG pages were retired with the service. TK search and
    # reading now stay inside the workbench; only the still-live report
    # archive remains an external link.
    return {"links": [{"label": "日报列表", "url": "/reports/", "desc": "历史日报"}]}


def refresh_data() -> dict:
    """Run Xiaoxue's only approved result-refresh pipeline and read it back."""
    started_at = datetime.now()
    manifest = DATA_ROOT / "scripts" / f"data_readiness_manifest_{started_at:%Y-%m-%d}.json"
    try:
        completed = subprocess.run(
            [sys.executable, str(DATA_REFRESH_PIPELINE)], cwd=str(DATA_ROOT), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "message": "赛果与 TS 刷新超时；本次结果不确定，请交给小白排查。"}
    if not manifest.is_file():
        return {"ok": False, "status": "missing_manifest", "message": "刷新未产生就绪凭据，请交给小白排查。"}
    try:
        result = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "status": "invalid_manifest", "message": "刷新凭据无法读取，请交给小白排查。"}
    result_ok = bool(completed.returncode == 0 and result.get("ok"))
    return {
        "ok": result_ok,
        "status": "ok" if result_ok else "failed",
        "summary": "赛果和 TS 已刷新" if result_ok else "赛果或 TS 刷新失败，请交给小白排查。",
        "stages": result.get("stages", []),
        "readiness": result.get("readiness", {}),
    }


def index_path() -> str:
    return repository.index_path()
