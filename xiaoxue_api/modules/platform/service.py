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
    items = [
        {"label": "TK 概念图", "url": "http://42.193.177.127:8768/tk-graph", "desc": "力导向关系图"},
        {"label": "知识库面板", "url": "http://42.193.177.127:8768/dashboard", "desc": "TK 统计看板"},
        {"label": "日报列表", "url": "/reports/", "desc": "历史日报"},
    ]
    if team:
        items.append({"label": f"{team} 赛前分析", "url": f"http://42.193.177.127:8768/prematch?team={team}", "desc": "赛前舆论+BP预测"})
    items.extend([
        {"label": "版本理解", "url": "http://42.193.177.127:8768/version", "desc": "当前版本体系"},
        {"label": "战力排行", "url": "http://42.193.177.127:8768/ranking", "desc": "ELO 实时排名"},
    ])
    return {"links": items}


def index_path() -> str:
    return repository.index_path()
