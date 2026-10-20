from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ProjectIdentity:
    project: dict[str, Any]
    agent: dict[str, Any]

    @property
    def agent_id(self) -> str:
        return str(self.agent["agent_id"])

    @property
    def display_name(self) -> str:
        return str(self.agent["display_name"])

    @property
    def knowledge_namespace(self) -> str:
        return str(self.project["knowledge_namespace"])

    def resolve_path_template(self, template: str) -> str:
        values = {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "knowledge_namespace": self.knowledge_namespace,
            "project_id": str(self.project["project_id"]),
        }
        try:
            return template.format(**values)
        except KeyError as exc:
            raise ValueError(f"unknown project identity placeholder: {exc.args[0]}") from exc


def project_root() -> Path:
    configured = os.environ.get("ESPORTS_PROJECT_ROOT", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"project identity config must be an object: {path}")
    return payload


def load_project_identity(root: str | Path | None = None, adapter_id: str | None = None) -> ProjectIdentity:
    root_path = Path(root) if root is not None else project_root()
    project = _read_json(root_path / "config" / "project-contract.json")
    selected = adapter_id or os.environ.get("ESPORTS_AGENT_ADAPTER", "").strip()
    selected = selected or str(project.get("default_agent_adapter", "xiaoxue"))
    if not _AGENT_ID.fullmatch(selected):
        raise ValueError(f"invalid agent adapter id: {selected!r}")
    agent = _read_json(root_path / str(project["agent_adapter_dir"]) / f"{selected}.json")
    if agent.get("schema") != "esports-agent-adapter-v1":
        raise ValueError(f"invalid agent adapter schema: {selected}")
    if agent.get("agent_id") != selected:
        raise ValueError(f"agent adapter id mismatch: {selected}")
    for field in ("display_name",):
        if not str(agent.get(field, "")).strip():
            raise ValueError(f"missing agent adapter field: {field}")
    return ProjectIdentity(project=project, agent=agent)
