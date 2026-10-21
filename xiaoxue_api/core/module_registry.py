from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal


ModuleState = Literal["healthy", "pending", "broken", "disabled"]
CapabilityEffect = Literal[
    "read",
    "temporary",
    "live_search",
    "reversible_change",
    "write",
    "critical",
]
CapabilityResultStatus = Literal[
    "ok", "partial", "empty", "conflict", "unavailable", "error"
]

REQUIRED_MANIFEST_FIELDS = (
    "id",
    "name",
    "version",
    "purpose",
    "examples",
    "inputs",
    "effect",
    "reads",
    "writes",
    "output_schema",
    "source_policy",
    "settings",
    "dependencies",
    "health",
    "tests",
)
DELIVERY_REQUIRED_FIELDS = (
    "configuration",
    "refresh",
    "source",
    "projections",
    "agent_entry",
    "acceptance",
)
VALID_EFFECTS = {
    "read",
    "temporary",
    "live_search",
    "reversible_change",
    "write",
    "critical",
}
VALID_RESULT_STATUSES = {"ok", "partial", "empty", "conflict", "unavailable", "error"}


class ManifestValidationError(ValueError):
    reason_code = "invalid_module_manifest"


def _baseline_delivery(manifest: dict[str, Any]) -> dict[str, Any]:
    """Give every registered capability a truthful minimum change contract.

    A module with scheduled refreshes, mutable business data, or multiple
    consumer boundaries can override this with a fuller delivery declaration.
    The baseline never directs agent reasoning or conversation flow.
    """
    return {
        "mode": "baseline",
        "configuration": {"owner": f"xiaoxue_api.modules.{manifest['id']}.manifest"},
        "refresh": {"entry": "on_demand", "automation": "none"},
        "source": {"reads": list(manifest["reads"]), "writes": list(manifest["writes"])},
        "projections": [{"router": manifest["router"], "output_schema": dict(manifest["output_schema"])}],
        "agent_entry": {
            "gateway": "xiaoxue-product",
            "behavior": "小雪自主决定是否调用、如何组合和如何解释；合同不规定对话步骤。",
        },
        "acceptance": ["manifest_registered", "runtime_health", "product_mcp_discovery"],
    }


def normalize_manifest(raw: object, *, module_name: str = "") -> dict[str, Any]:
    """Validate and copy one declarative capability manifest."""

    if not isinstance(raw, dict):
        raise ManifestValidationError(f"{module_name or 'module'} manifest must be a mapping")
    manifest = dict(raw)
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise ManifestValidationError(
            f"{module_name or manifest.get('id') or 'module'} manifest missing: {', '.join(missing)}"
        )
    for field in ("id", "name", "version", "purpose"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            raise ManifestValidationError(f"manifest.{field} must be a non-empty string")
        manifest[field] = manifest[field].strip()
    if module_name and manifest["id"] != module_name:
        raise ManifestValidationError(
            f"manifest id {manifest['id']!r} does not match module directory {module_name!r}"
        )
    if manifest["effect"] not in VALID_EFFECTS:
        raise ManifestValidationError(f"unsupported effect: {manifest['effect']!r}")
    for field in ("examples", "reads", "writes", "dependencies", "tests"):
        if not isinstance(manifest[field], list):
            raise ManifestValidationError(f"manifest.{field} must be a list")
        manifest[field] = list(manifest[field])
    for field in ("inputs", "output_schema", "source_policy", "settings", "health"):
        if not isinstance(manifest[field], dict):
            raise ManifestValidationError(f"manifest.{field} must be a mapping")
        manifest[field] = dict(manifest[field])
    manifest["order"] = int(manifest.get("order", 1000))
    manifest["router"] = str(
        manifest.get("router") or f"xiaoxue_api.modules.{manifest['id']}.presentation"
    )
    manifest["critical"] = bool(manifest.get("critical", False))
    if "delivery" not in manifest:
        manifest["delivery"] = _baseline_delivery(manifest)
    else:
        delivery = manifest["delivery"]
        if not isinstance(delivery, dict):
            raise ManifestValidationError("manifest.delivery must be a mapping")
        missing_delivery = [field for field in DELIVERY_REQUIRED_FIELDS if field not in delivery]
        if missing_delivery:
            raise ManifestValidationError(
                f"manifest.delivery missing: {', '.join(missing_delivery)}"
            )
        for field in ("configuration", "refresh", "source", "agent_entry"):
            if not isinstance(delivery[field], dict):
                raise ManifestValidationError(f"manifest.delivery.{field} must be a mapping")
        for field in ("projections", "acceptance"):
            if not isinstance(delivery[field], list) or not delivery[field]:
                raise ManifestValidationError(f"manifest.delivery.{field} must be a non-empty list")
        manifest["delivery"] = dict(delivery)
    return manifest


def capability_result(
    status: CapabilityResultStatus,
    *,
    summary: str,
    data: Any = None,
    sources: list[dict[str, Any]] | None = None,
    effects: dict[str, Any] | None = None,
    readback: Any = None,
    gaps: list[dict[str, Any] | str] | None = None,
    conflicts: list[dict[str, Any] | str] | None = None,
    error: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable result envelope without changing legacy API payloads in place."""

    if status not in VALID_RESULT_STATUSES:
        raise ValueError(f"unsupported capability result status: {status!r}")
    return {
        "status": status,
        "summary": summary,
        "data": data,
        "sources": list(sources or []),
        "effects": dict(effects or {}),
        "readback": readback,
        "gaps": list(gaps or []),
        "conflicts": list(conflicts or []),
        "error": error,
        "trace": dict(trace or {}),
    }


@dataclass(frozen=True)
class ModuleStatus:
    id: str
    name: str
    status: ModuleState
    version: str = ""
    effect: str = ""
    reason_code: str = ""
    message: str = ""
    critical: bool = False
    checked_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checked_at"] = self.checked_at or datetime.now().isoformat(timespec="seconds")
        return payload


class ModuleRegistry:
    """Register capability contracts and collect independent module states."""

    def __init__(self) -> None:
        self._manifests: dict[str, dict[str, Any]] = {}
        self._modules: dict[str, ModuleStatus] = {}

    def register_manifest(self, raw: object, *, module_name: str = "") -> dict[str, Any]:
        manifest = normalize_manifest(raw, module_name=module_name)
        self._manifests[manifest["id"]] = manifest
        return manifest

    def manifest(self, module_id: str) -> dict[str, Any] | None:
        item = self._manifests.get(module_id)
        return dict(item) if item else None

    def manifests(self) -> dict[str, dict[str, Any]]:
        return {module_id: dict(item) for module_id, item in self._manifests.items()}

    def healthy(self, module_id: str, name: str = "", *, message: str = "") -> None:
        self._set(self._status(module_id, name, "healthy", message=message))

    def broken(
        self,
        module_id: str,
        name: str = "",
        *,
        reason_code: str,
        message: str,
        critical: bool | None = None,
    ) -> None:
        self._set(
            self._status(
                module_id,
                name,
                "broken",
                reason_code=reason_code,
                message=message,
                critical=critical,
            )
        )

    def disabled(self, module_id: str, name: str = "", *, message: str = "") -> None:
        self._set(self._status(module_id, name, "disabled", message=message))

    def pending(
        self,
        module_id: str,
        name: str = "",
        *,
        reason_code: str,
        message: str,
    ) -> None:
        self._set(
            self._status(module_id, name, "pending", reason_code=reason_code, message=message)
        )

    def _status(
        self,
        module_id: str,
        name: str,
        status: ModuleState,
        *,
        reason_code: str = "",
        message: str = "",
        critical: bool | None = None,
    ) -> ModuleStatus:
        manifest = self._manifests.get(module_id) or {}
        return ModuleStatus(
            id=module_id,
            name=name or manifest.get("name") or module_id,
            status=status,
            version=manifest.get("version") or "",
            effect=manifest.get("effect") or "",
            reason_code=reason_code,
            message=message,
            critical=manifest.get("critical", False) if critical is None else critical,
        )

    def _set(self, status: ModuleStatus) -> None:
        self._modules[status.id] = status

    def as_dict(self) -> dict[str, Any]:
        modules = {module_id: status.as_dict() for module_id, status in self._modules.items()}
        critical_broken = any(
            item.status == "broken" and item.critical for item in self._modules.values()
        )
        any_broken = any(item.status == "broken" for item in self._modules.values())
        overall = "broken" if critical_broken else "degraded" if any_broken else "healthy"
        return {
            "status": overall,
            "modules": modules,
            "capabilities": {
                module_id: {
                    "id": item["id"],
                    "name": item["name"],
                    "version": item["version"],
                    "purpose": item["purpose"],
                    "effect": item["effect"],
                    "reads": list(item["reads"]),
                    "writes": list(item["writes"]),
                    "dependencies": list(item["dependencies"]),
                    "delivery": dict(item.get("delivery") or {}),
                }
                for module_id, item in self._manifests.items()
            },
        }
