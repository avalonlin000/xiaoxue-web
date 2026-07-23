from __future__ import annotations

from datetime import datetime

from xiaoxue_api.core.health_projection import project_module_health
from xiaoxue_api.modules.daily_content.public import get_operating_state

from . import repository


_boot_status = {}


def configure_boot_status(status: dict) -> None:
    global _boot_status
    _boot_status = dict(status)


def health() -> dict:
    checks = repository.collect_checks()
    checks["daily_operation"] = get_operating_state()
    module_health = project_module_health(checks, _boot_status)
    return {
        "ok": all(item.get("ok", True) if isinstance(item, dict) else bool(item) for item in checks.values()),
        "status": module_health["status"], "modules": module_health["modules"],
        "service": "xiaoxue-workbench-api", "time": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
    }


def links(team: str = "") -> dict:
    # 8768 legacy RAG pages were retired with the service. TK search and
    # reading now stay inside the workbench; only the still-live report
    # archive remains an external link.
    return {"links": [{"label": "日报列表", "url": "/reports/", "desc": "历史日报"}]}


def index_path() -> str:
    return repository.index_path()
