#!/usr/bin/env python3
"""Validate the single project-level Xiaoxue module contract and its references."""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xiaoxue_api.core.module_loader import discover_module_names  # noqa: E402
from xiaoxue_api.core.product_modules import load_module_contract  # noqa: E402


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    payload = load_module_contract()
    modules = payload["modules"]
    project_contract = json.loads((ROOT / "config/project-contract.json").read_text(encoding="utf-8"))
    if project_contract.get("module_contract") != "config/module-contract.json":
        fail("project-contract.json 未指向唯一模块合同")

    guide = ROOT / str(payload.get("model_usage_guide") or "")
    canonical = ROOT / "AGENTS.md"
    if not guide.is_file() or guide.resolve() != canonical.resolve():
        fail("模型项目使用说明未指向根 AGENTS.md")
    if project_contract.get("rules_source") != "AGENTS.md":
        fail("项目约定未指向根 AGENTS.md")
    rule_refs = project_contract.get("rules") or {}
    if not rule_refs or any(not str(value).startswith("AGENTS.md#") for value in rule_refs.values()):
        fail("project-contract.json 仍维护独立规则正文")
    legacy_guide = ROOT / "docs/小雪项目总使用说明.md"
    if "[AGENTS.md](../AGENTS.md)" not in legacy_guide.read_text(encoding="utf-8"):
        fail("旧使用说明未转向根 AGENTS.md")
    skill = Path("/home/ubuntu/.agents/skills/小雪/SKILL.md")
    skill_text = skill.read_text(encoding="utf-8")
    if guide.name not in skill_text and legacy_guide.name not in skill_text:
        fail("根 Skill 未接入项目约定或兼容入口")

    backend_modules = set(discover_module_names())
    missing_backend = {
        name
        for module in modules
        for name in module["compatibility"].get("backend_capabilities", [])
        if name not in backend_modules
    }
    if missing_backend:
        fail(f"模块合同引用不存在的后端能力：{sorted(missing_backend)}")

    source = (ROOT / "src/app/module-catalog.js").read_text(encoding="utf-8")
    frontend_ids: set[str] = set()
    for raw in re.findall(r"contract_ids:\s*(\[[^\]]+\])", source):
        frontend_ids.update(ast.literal_eval(raw))
    contract_ids = {
        module["id"] for module in modules
        if module["compatibility"].get("frontend_loaders")
    }
    if frontend_ids != contract_ids:
        fail(f"前端模块映射不完整：缺少 {sorted(contract_ids - frontend_ids)}，多出 {sorted(frontend_ids - contract_ids)}")

    required_sections = ("source_of_truth", "read_capability", "bounded_write_capability", "readback_capability")
    for module in modules:
        if any(not module.get(section) for section in required_sections):
            fail(f"模块 {module['id']} 的正源/读写/读回合同不完整")
        if not module.get("analysis_capability"):
            fail(f"模块 {module['id']} 缺少 analysis_capability")
        if not module["readback_capability"].get("checks"):
            fail(f"模块 {module['id']} 缺少读回检查")

    print(json.dumps({
        "schema": payload["schema"],
        "module_count": len(modules),
        "modules": [{"id": item["id"], "status": item["status"]} for item in modules],
        "backend_capabilities_checked": sorted(backend_modules),
        "frontend_contract_ids": sorted(frontend_ids),
        "model_usage_guide": str(guide.relative_to(ROOT)),
        "result": "ok",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
