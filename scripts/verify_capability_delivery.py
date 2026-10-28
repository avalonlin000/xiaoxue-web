#!/usr/bin/env python3
"""Verify declared Xiaoxue capability delivery contracts.

Contracts protect the plumbing around autonomous agent behavior: source,
projection, product entry and maintenance. They never prescribe when Xiaoxue
must call a capability or how she should reason about its result.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path("/home/ubuntu/xiaoxue-web")
MCP_PYTHON = ROOT / ".venv-mcp" / "bin" / "python"
MCP_SCRIPT = ROOT / "scripts" / "hermes" / "xiaoxue_product_mcp.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_MCP_DISCOVERY: dict[str, Any] | None = None
_MISSING = object()


def _nested_value(value: Any, path: str) -> Any:
    """Return a dot-delimited nested value, preserving missing-vs-null."""
    current = value
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _manifest(capability: str) -> dict[str, Any]:
    raw = importlib.import_module(f"xiaoxue_api.modules.{capability}.manifest").MODULE
    from xiaoxue_api.core.module_registry import normalize_manifest
    return normalize_manifest(raw, module_name=capability)


def _capability_names() -> list[str]:
    from xiaoxue_api.core.module_loader import discover_module_names
    return list(discover_module_names())


def _health(api_base: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{api_base.rstrip('/')}/api/health", timeout=15) as response:
        return json.load(response)


def _manifest_registered(capability: str) -> dict[str, Any]:
    manifest = _manifest(capability)
    return {"module": manifest["id"], "mode": manifest["delivery"].get("mode", "full")}


def _runtime_health(capability: str, api_base: str) -> dict[str, Any]:
    payload = _health(api_base)
    module = payload.get("modules", {}).get(capability) or {}
    if module.get("status") not in {"healthy", "disabled"}:
        raise AssertionError(f"{capability} runtime status: {module.get('status')!r}")
    delivery = payload.get("capabilities", {}).get(capability, {}).get("delivery")
    if not delivery:
        raise AssertionError(f"{capability} delivery contract is absent from runtime health")
    return {"status": module["status"], "mode": delivery.get("mode", "full")}


def _product_mcp_discovery() -> dict[str, Any]:
    global _MCP_DISCOVERY
    if _MCP_DISCOVERY is not None:
        return _MCP_DISCOVERY
    probe = """
import importlib.util
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('xiaoxue_project_mcp', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({'server': 'xiaoxue-product', 'status': 'discovered', 'tools': list(module.PUBLIC_TOOL_FUNCTIONS)}, ensure_ascii=False))
"""
    result = subprocess.run(
        [str(MCP_PYTHON), "-c", probe, str(MCP_SCRIPT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"xiaoxue-product project MCP discovery failed: {result.stdout[-1000:]}")
    try:
        _MCP_DISCOVERY = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("xiaoxue-product project MCP returned invalid discovery output") from exc
    return _MCP_DISCOVERY


def _snapshot_readback(contract: dict[str, Any]) -> dict[str, Any]:
    source = contract["source"]
    from xiaoxue_api.modules.team.ts.repository import active_stage

    stage = active_stage()
    with sqlite3.connect(source["database"]) as conn:
        rows = conn.execute(
            f"SELECT region, COUNT(*) FROM {source['snapshot']} WHERE stage=? GROUP BY region",
            (stage,),
        ).fetchall()
    counts = dict(rows)
    if not counts:
        raise AssertionError(f"snapshot missing rows for active stage {stage!r}")
    return {"stage": stage, "rows": counts}


def _api_projection(contract: dict[str, Any], api_base: str) -> dict[str, Any]:
    projection = contract["projections"][0]
    url = f"{api_base.rstrip('/')}{projection['endpoint']}?scope=all&limit=80"
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = json.load(response)
    teams = payload.get("teams", [])
    stage_names = sorted({str(team.get("ts_stage") or "") for team in teams} - {"", "legacy"})
    if len(stage_names) != 1:
        raise AssertionError(f"API ts_stage labels inconsistent: {stage_names}")
    stage_teams = [team for team in teams if str(team.get("ts_stage") or "") == stage_names[0]]
    if not stage_teams:
        raise AssertionError("API contains no current-stage TS teams")
    missing = [
        field
        for field in projection["fields"]
        if any(_nested_value(team, field) is _MISSING for team in stage_teams)
    ]
    if missing or any(not team.get("ts_l1") or not team.get("ts_l2") for team in stage_teams):
        raise AssertionError(f"API projection incomplete: {missing}")
    return {"endpoint": projection["endpoint"], "teams": len(stage_teams)}


async def _agent_tool_readback(contract: dict[str, Any]) -> dict[str, Any]:
    from scripts.hermes.xiaoxue_product_mcp import xiaoxue_get_team

    result = json.loads(await xiaoxue_get_team(team="KT"))
    required = contract["agent_entry"]["fields"]
    values = {path: _nested_value(result, path) for path in required}
    missing = [path for path, value in values.items() if value is _MISSING]
    if missing:
        raise AssertionError(f"agent entry missing fields: {', '.join(missing)}")
    return {"tool": contract["agent_entry"]["tool"], "team": "KT", "fields": values}


def _automation_entry(contract: dict[str, Any]) -> dict[str, Any]:
    refresh = contract["refresh"]
    text = Path(refresh["automation"]).read_text(encoding="utf-8")
    expected = Path(refresh["entry"].split("::", 1)[0]).name
    if expected not in text:
        raise AssertionError(f"automation no longer references {expected}")
    return {"entry": refresh["entry"]}


def verify(capability: str, api_base: str) -> dict[str, Any]:
    manifest = _manifest(capability)
    contract = manifest["delivery"]
    checkers = {
        "manifest_registered": lambda: _manifest_registered(capability),
        "runtime_health": lambda: _runtime_health(capability, api_base),
        "product_mcp_discovery": _product_mcp_discovery,
        "snapshot_readback": lambda: _snapshot_readback(contract),
        "api_projection": lambda: _api_projection(contract, api_base),
        "agent_tool_readback": lambda: asyncio.run(_agent_tool_readback(contract)),
        "automation_entry": lambda: _automation_entry(contract),
    }
    results = {}
    for check in contract["acceptance"]:
        results[check] = checkers[check]()
    return {"capability": capability, "mode": contract.get("mode", "full"), "status": "ok", "checks": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capability", choices=["all", *_capability_names()])
    parser.add_argument("--api-base", default="http://127.0.0.1:8880")
    args = parser.parse_args()
    names = _capability_names() if args.capability == "all" else [args.capability]
    results = [verify(name, args.api_base) for name in names]
    print(json.dumps({"status": "ok", "capabilities": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
