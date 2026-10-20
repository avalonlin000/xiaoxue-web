"""Load and validate the project-level user module contract.

Backend capability manifests remain the runtime router contract. This catalog
is the single project-level mapping from a user-facing module to its source,
entry points, bounded writes, readback and consumers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REQUIRED_MODULE_FIELDS = (
    "id",
    "display_name",
    "purpose",
    "user_entry",
    "agent_entry",
    "source_of_truth",
    "read_capability",
    "bounded_write_capability",
    "readback_capability",
    "extension_kind",
    "consumers",
    "status",
    "compatibility",
)
REQUIRED_CONTRACT_FIELDS = ("tool_contract", "result_contract")
VALID_STATUSES = {"available", "partial", "blocked", "deprecated"}
VALID_EXTENSION_KINDS = {"ordinary_content", "structural_capability"}
REQUIRED_OBJECT_ADAPTERS = (
    "entities",
    "events",
    "information_sources",
    "result_sources",
    "methods",
    "ordinary_tk",
    "trading_tk",
    "judgment_fields",
    "presentation",
)


class ModuleContractError(ValueError):
    reason_code = "invalid_project_module_contract"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModuleContractError(f"模块合同文件无法读取：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ModuleContractError(f"模块合同不是有效 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise ModuleContractError("模块合同根节点必须是对象")
    return payload


def validate_module_contract(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ModuleContractError("模块合同根节点必须是对象")
    if payload.get("schema") != "xiaoxue-module-contract-v1":
        raise ModuleContractError("模块合同 schema 不匹配")
    missing_contract = [field for field in REQUIRED_CONTRACT_FIELDS if not isinstance(payload.get(field), dict)]
    if missing_contract:
        raise ModuleContractError(f"项目模块合同缺少：{', '.join(missing_contract)}")
    statuses = payload["result_contract"].get("statuses")
    if statuses != ["ok", "partial", "empty", "conflict", "unavailable", "error"]:
        raise ModuleContractError("项目结果合同状态集合不匹配")
    if payload["tool_contract"].get("mcp") != "xiaoxue-product":
        raise ModuleContractError("项目工具合同未指向唯一 xiaoxue-product MCP")
    modules = payload.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ModuleContractError("模块合同必须包含非空 modules")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(modules):
        if not isinstance(raw, dict):
            raise ModuleContractError(f"modules[{index}] 必须是对象")
        missing = [field for field in REQUIRED_MODULE_FIELDS if field not in raw]
        if missing:
            raise ModuleContractError(f"modules[{index}] 缺少：{', '.join(missing)}")
        module = dict(raw)
        module_id = str(module["id"]).strip()
        if not module_id or module_id in seen:
            raise ModuleContractError(f"模块 ID 缺失或重复：{module_id or index}")
        if module["status"] not in VALID_STATUSES:
            raise ModuleContractError(f"模块 {module_id} status 无效：{module['status']}")
        if module["extension_kind"] not in VALID_EXTENSION_KINDS:
            raise ModuleContractError(f"模块 {module_id} extension_kind 无效")
        for field in ("user_entry", "agent_entry", "source_of_truth", "read_capability", "bounded_write_capability", "readback_capability", "compatibility"):
            if not isinstance(module[field], dict) or not module[field]:
                raise ModuleContractError(f"模块 {module_id} 的 {field} 必须是非空对象")
        for field in ("consumers",):
            if not isinstance(module[field], list) or not module[field]:
                raise ModuleContractError(f"模块 {module_id} 的 {field} 必须是非空列表")
        if not isinstance(module["compatibility"].get("backend_capabilities"), list):
            raise ModuleContractError(f"模块 {module_id} 缺少 compatibility.backend_capabilities")
        seen.add(module_id)
        normalized.append(module)
    result = dict(payload)
    result["modules"] = normalized
    return result


@lru_cache(maxsize=1)
def load_module_contract() -> dict[str, Any]:
    root = project_root()
    project_contract = _read_json(root / "config" / "project-contract.json")
    relative_path = str(project_contract.get("module_contract") or "config/module-contract.json")
    path = root / relative_path
    return validate_module_contract(_read_json(path))


@lru_cache(maxsize=1)
def load_project_contract() -> dict[str, Any]:
    return _read_json(project_root() / "config" / "project-contract.json")


def object_catalog() -> dict[str, Any]:
    catalog = load_project_contract().get("object_catalog")
    if not isinstance(catalog, dict) or catalog.get("contract") != "shared-object-package-v1":
        raise ModuleContractError("项目对象目录合同缺失或版本不匹配")
    if not isinstance(catalog.get("shared_lifecycle"), list) or not catalog["shared_lifecycle"]:
        raise ModuleContractError("项目对象目录缺少 shared_lifecycle")
    adapters = catalog.get("required_adapters")
    if not isinstance(adapters, list) or not set(REQUIRED_OBJECT_ADAPTERS).issubset(adapters):
        raise ModuleContractError("项目对象目录缺少统一适配器合同")
    objects = catalog.get("objects")
    if not isinstance(objects, dict) or not objects:
        raise ModuleContractError("项目对象目录必须包含 objects")
    return dict(catalog)


def module_catalog() -> list[dict[str, Any]]:
    return [dict(module) for module in load_module_contract()["modules"]]


def module_by_id(module_id: str) -> dict[str, Any] | None:
    return next((module for module in module_catalog() if module["id"] == module_id), None)


def public_module_catalog() -> dict[str, Any]:
    """Return the catalog for project tools/observers without implementation paths."""

    payload = load_module_contract()
    modules = []
    for module in payload["modules"]:
        item = dict(module)
        source = dict(item["source_of_truth"])
        source.pop("state", None)
        item["source_of_truth"] = source
        modules.append(item)
    return {
        "schema": payload["schema"],
        "version": payload["version"],
        "model_usage_guide": payload.get("model_usage_guide", ""),
        "tool_contract": dict(payload["tool_contract"]),
        "result_contract": dict(payload["result_contract"]),
        "object_catalog": object_catalog(),
        "modules": modules,
    }
