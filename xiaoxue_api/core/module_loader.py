from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from typing import Any

import xiaoxue_api.modules as modules_package
from xiaoxue_api.core.module_registry import normalize_manifest



def discover_module_names() -> tuple[str, ...]:
    """Discover capability packages; a valid manifest decides whether they can load."""

    names = [
        item.name
        for item in pkgutil.iter_modules(modules_package.__path__)
        if not item.name.startswith("_")
    ]
    return tuple(sorted(names))


def attach_feature_routers(
    app,
    modules: Iterable[str] | None = None,
    loader: Callable[[str], Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Attach manifest-registered routers independently.

    One invalid manifest or import failure is reported without stopping the
    application shell or the remaining capabilities.
    """

    load = loader or importlib.import_module
    module_names = tuple(modules) if modules is not None else discover_module_names()
    statuses: dict[str, dict[str, Any]] = {}
    registered: list[tuple[str, dict[str, Any]]] = []

    for module_name in module_names:
        manifest_target = f"xiaoxue_api.modules.{module_name}.manifest"
        try:
            imported_manifest = load(manifest_target)
            manifest = normalize_manifest(
                getattr(imported_manifest, "MODULE", None), module_name=module_name
            )
            registered.append((module_name, manifest))
        except Exception as exc:
            statuses[module_name] = {
                "status": "broken",
                "reason_code": getattr(exc, "reason_code", "module_manifest_load_failed"),
                "message": f"{module_name} 能力声明加载失败：{exc}",
            }

    for module_name, manifest in sorted(registered, key=lambda item: item[1]["order"]):
        module_id = manifest["id"]
        try:
            imported: Any = load(manifest["router"])
            app.include_router(imported.router)
            statuses[module_id] = {
                "status": "healthy",
                "message": "",
                "manifest": manifest,
            }
        except Exception as exc:
            statuses[module_id] = {
                "status": "broken",
                "reason_code": "module_load_failed",
                "message": f"{module_id} 模块加载失败：{exc}",
                "manifest": manifest,
            }
    return statuses
