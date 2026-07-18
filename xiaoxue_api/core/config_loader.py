from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class IsolatedConfigs:
    config: dict
    modules: dict[str, dict]


def load_isolated_configs(root: str | Path) -> IsolatedConfigs:
    root_path = Path(root)
    merged: dict = {"schema": "xiaoxue-workflows-v1"}
    modules: dict[str, dict] = {}

    if not root_path.exists():
        return IsolatedConfigs(config=merged, modules={})

    for module_dir in sorted(path for path in root_path.iterdir() if path.is_dir()):
        config_path = module_dir / "config.json"
        if not config_path.exists():
            continue
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("module config must be an object")
            overlap = set(merged).intersection(payload) - {"schema"}
            if overlap:
                raise ValueError(f"duplicate config keys: {', '.join(sorted(overlap))}")
            merged.update(payload)
            modules[module_dir.name] = {"status": "healthy", "path": str(config_path)}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            modules[module_dir.name] = {
                "status": "broken",
                "path": str(config_path),
                "reason_code": "invalid_config",
                "message": str(exc),
            }
    return IsolatedConfigs(config=merged, modules=modules)
