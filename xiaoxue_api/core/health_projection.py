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
    outcomes = [_check_ok(checks.get(key)) for key in required_checks]
    mode = health.get("check_mode", "all")
    available = any(outcomes) if mode == "any" else all(outcomes)
    if available:
        registry.healthy(module_id, message=health.get("message") or "")
        return

    registry.broken(
        module_id,
        reason_code=health.get("reason_code") or "dependency_unavailable",
        message=health.get("unavailable_message") or "该模块当前不可用，其他模块继续运行",
    )


def _check_ok(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("ok"))
    return bool(value)
