from __future__ import annotations

import importlib
from collections.abc import Callable


ACTIVE_MODULES = (
    "lineup", "market_notes", "team_data", "daily_content",
    "profiles", "tk_knowledge", "fundamentals", "analyst", "platform", "weread_bridge",
    "pre_match", "legacy_trades",
    "current_event",
)


def attach_feature_routers(app, modules=ACTIVE_MODULES, loader: Callable[[str], object] | None = None) -> dict:
    """Attach each module independently so one import failure cannot stop the application shell."""
    load = loader or importlib.import_module
    statuses = {}
    for module_name in modules:
        target = f"xiaoxue_api.modules.{module_name}.presentation"
        try:
            imported = load(target)
            app.include_router(imported.router)
            statuses[module_name] = {"status": "healthy", "message": ""}
        except Exception as exc:
            statuses[module_name] = {
                "status": "broken",
                "reason_code": "module_load_failed",
                "message": f"{module_name} 模块加载失败：{exc}",
            }
    return statuses
