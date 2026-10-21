from __future__ import annotations

from typing import Any

from xiaoxue_api.core.module_registry import ModuleRegistry


def project_module_health(checks: dict, boot_status: dict | None = None) -> dict:
    """Project runtime health from registered capability manifests."""

    registry = ModuleRegistry()
    statuses = boot_status or {}

    for fallback_id, boot in statuses.items():
        manifest = boot.get("manifest") if isinstance(boot, dict) else None
        if not isinstance(manifest, dict):
            registry.broken(
                fallback_id,
                reason_code=(boot or {}).get("reason_code") or "module_manifest_unavailable",
                message="该能力没有可用声明，其他模块继续运行",
            )
            continue

        manifest = registry.register_manifest(manifest, module_name=manifest["id"])
        module_id = manifest["id"]
        if boot.get("status") == "broken":
            registry.broken(
                module_id,
                reason_code=boot.get("reason_code") or "module_load_failed",
                message="该模块加载失败，其他模块继续运行",
            )
            continue
        _project_manifest_health(registry, manifest, checks)

    return registry.as_dict()


def _project_manifest_health(
    registry: ModuleRegistry,
    manifest: dict[str, Any],
    checks: dict[str, Any],
) -> None:
    module_id = manifest["id"]
    health = manifest["health"]

    if health.get("state") == "disabled":
        registry.disabled(module_id, message=health.get("message") or "当前已停用")
        return

    pause_key = health.get("pause_check")
    if pause_key:
        pause_value = checks.get(pause_key) or {}
        if pause_value.get("state") == health.get("pause_state"):
            registry.disabled(
                module_id,
                message=pause_value.get("message") or health.get("message") or "当前已暂停",
            )
            return

    required_checks = health.get("checks") or []
    states = {key: _check_state(checks.get(key)) for key in required_checks}
    mode = health.get("check_mode", "all")
    values = list(states.values())
    if not values:
        # A capability that declares no runtime check is healthy by declaration.
        registry.healthy(module_id, message=health.get("message") or "")
        return
    available = any(value == "ok" for value in values) if mode == "any" else all(value == "ok" for value in values)
    if available:
        registry.healthy(module_id, message=health.get("message") or "")
        return

    if all(value in {"ok", "deferred"} for value in values):
        # Dependencies that are simply not produced yet: report the wait, not a fault.
        deferred_message = next(
            (checks[key].get("message") for key in required_checks if states[key] == "deferred"), ""
        )
        registry.pending(
            module_id,
            reason_code=health.get("deferred_reason_code") or "dependency_not_due",
            message=deferred_message or health.get("deferred_message") or "依赖内容按计划生成中",
        )
        return

    registry.broken(
        module_id,
        reason_code=health.get("reason_code") or "dependency_unavailable",
        message=health.get("unavailable_message") or "该模块当前不可用，其他模块继续运行",
    )


def _check_state(value: Any) -> str:
    """ok / deferred (not produced yet) / failed."""
    if isinstance(value, dict):
        if value.get("state") == "not_due" and not value.get("ok"):
            return "deferred"
        return "ok" if value.get("ok") else "failed"
    return "ok" if value else "failed"
