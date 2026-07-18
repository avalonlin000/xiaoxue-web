from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal


ModuleState = Literal["healthy", "broken", "disabled"]


@dataclass(frozen=True)
class ModuleStatus:
    id: str
    name: str
    status: ModuleState
    reason_code: str = ""
    message: str = ""
    critical: bool = False
    checked_at: str = ""

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["checked_at"] = self.checked_at or datetime.now().isoformat(timespec="seconds")
        return payload


class ModuleRegistry:
    """Collect independent module states without turning one failure into a global outage."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleStatus] = {}

    def healthy(self, module_id: str, name: str, *, message: str = "") -> None:
        self._set(ModuleStatus(module_id, name, "healthy", message=message))

    def broken(
        self,
        module_id: str,
        name: str,
        *,
        reason_code: str,
        message: str,
        critical: bool = False,
    ) -> None:
        self._set(
            ModuleStatus(
                module_id,
                name,
                "broken",
                reason_code=reason_code,
                message=message,
                critical=critical,
            )
        )

    def disabled(self, module_id: str, name: str, *, message: str = "") -> None:
        self._set(ModuleStatus(module_id, name, "disabled", message=message))

    def _set(self, status: ModuleStatus) -> None:
        self._modules[status.id] = status

    def as_dict(self) -> dict:
        modules = {module_id: status.as_dict() for module_id, status in self._modules.items()}
        critical_broken = any(
            item.status == "broken" and item.critical for item in self._modules.values()
        )
        any_broken = any(item.status == "broken" for item in self._modules.values())
        overall = "broken" if critical_broken else "degraded" if any_broken else "healthy"
        return {"status": overall, "modules": modules}
