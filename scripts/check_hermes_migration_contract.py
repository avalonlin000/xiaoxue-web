#!/usr/bin/env python3
"""Verify Xiaoxue's project-to-Hermes migration contract.

The check can inspect a verified-delivery package before activation or the
live targets after activation. It is read-only and deliberately fails when a
runtime Skill still points at the retired TK service or a nested Hermes skill
path that no longer exists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml


REQUIRED_API_PATHS = {
    "/api/daily-content",
    "/api/schedules",
    "/api/teams",
    "/api/tk/search",
    "/api/tk/entry/{filename}",
    "/api/team-trading-notes/{team}",
    "/api/current-event/match-run/active",
    "/api/current-event/match-run/pause",
    "/api/current-event/match-run/entry",
    "/api/trading-tk",
    "/api/trading-tk/{filename}",
    "/api/research/subjects",
    "/api/research/subjects/{subject_id}",
    "/api/research/subjects/{subject_id}/events",
    "/api/research/subjects/{subject_id}/materials",
    "/api/research/subjects/{subject_id}/digests",
    "/api/research/subjects/{subject_id}/notes",
    "/api/research/subjects/{subject_id}/reviews",
    "/api/research/match-brief",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_MCP_PYTHON = PROJECT_ROOT / ".venv-mcp" / "bin" / "python"
PROJECT_MCP_SCRIPT = PROJECT_ROOT / "scripts" / "hermes" / "xiaoxue_product_mcp.py"
MCP_TOOL_SNAPSHOT = PROJECT_ROOT / "tests" / "fixtures" / "xiaoxue_product_mcp_tools.json"
PRODUCT_BOUNDARY_PLUGIN = Path("/home/ubuntu/.hermes/plugins/xiaoxue-product-boundary")
RETIRED_RUNTIME_MARKERS = (
    "localhost:8768",
    "127.0.0.1:8768",
    "/home/ubuntu/.hermes/skills/xiaoxue/",
    "/home/ubuntu/.hermes/skills/gaming/",
)
REQUIRED_ENABLED_SKILLS = {
    "xiaoxue",
    "lol-lineup-analysis",
    "junjun-trading-system",
    "xiaoxue-data-reconciliation",
    "xiaoxue-knowledge-loop",
    "xiaoxue-retrospective",
    "xiaoxue-knowledge-maintenance",
    "xiaoxue-version-team-brief",
}
REQUIRED_DISABLED_SKILLS = {
    "xiaoxue-dev-index",
}

LIVE_TARGETS = {
    "hermes-config": Path("/home/ubuntu/.hermes/config.yaml"),
    "xiaoxue-product-mcp": Path("/home/ubuntu/xiaoxue-web/scripts/hermes/xiaoxue_product_mcp.py"),
    "xiaoxue-root": Path("/home/ubuntu/.agents/skills/小雪/SKILL.md"),
    "xiaoxue-dev-index": Path("/home/ubuntu/.agents/skills/engineering/xiaoxue-dev-index/SKILL.md"),
    "lol-knowledge-engine": Path("/home/ubuntu/.agents/skills/esports/knowledge/lol-knowledge-engine/SKILL.md"),
}


def _load_package(package: Path | None) -> tuple[dict[str, Path], list[Path]]:
    if package is None:
        paths = dict(LIVE_TARGETS)
        runtime_docs = [
            Path("/home/ubuntu/.agents/skills/小雪"),
            Path("/home/ubuntu/.agents/skills/engineering/xiaoxue-dev-index"),
            Path("/home/ubuntu/.agents/skills/esports/knowledge/lol-knowledge-engine"),
        ]
        return paths, runtime_docs

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {item["id"]: Path(item["staged"]) for item in manifest.get("artifacts", [])}
    targets = dict(LIVE_TARGETS)
    targets.update(artifacts)
    if "xiaoxue-skill" in artifacts:
        targets["xiaoxue-root"] = artifacts["xiaoxue-skill"]
    staged_runtime_docs = [
        path for artifact_id, path in artifacts.items()
        if artifact_id in {
            "xiaoxue-root", "xiaoxue-skill", "xiaoxue-toolkit", "xiaoxue-workflow", "lol-knowledge-engine",
            "xiaoxue-reference", "daily-inspection", "xiaoxue-legacy", "infra-services",
            "operations-manual", "repair-pipeline", "skills-audit", "workbench-api",
            "knowledge-engine-ref", "knowledge-import-audit", "restart-blueprint",
        }
    ]
    runtime_docs = staged_runtime_docs or [
        Path("/home/ubuntu/.agents/skills/小雪"),
        Path("/home/ubuntu/.agents/skills/engineering/xiaoxue-dev-index"),
        Path("/home/ubuntu/.agents/skills/esports/knowledge/lol-knowledge-engine"),
    ]
    return targets, runtime_docs


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"YAML 根结构无效：{path}")
    return data


def _skill_names() -> set[str]:
    names: set[str] = set()
    for skill_file in Path("/home/ubuntu/.agents/skills").rglob("SKILL.md"):
        text = skill_file.read_text(encoding="utf-8", errors="replace")[:4000]
        match = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
        if match:
            names.add(match.group(1).strip())
    return names


def _check_config(config: dict[str, Any], mcp_target: Path) -> list[str]:
    errors: list[str] = []
    server = (config.get("mcp_servers") or {}).get("xiaoxue-product") or {}
    expected_command = str(PROJECT_MCP_PYTHON)
    expected_script = "/home/ubuntu/xiaoxue-web/scripts/hermes/xiaoxue_product_mcp.py"
    if server.get("command") != expected_command:
        errors.append("xiaoxue-product MCP 没有使用项目 .venv-mcp")
    if expected_script not in (server.get("args") or []):
        errors.append("xiaoxue-product MCP 没有指向小雪正式适配器")
    include_value = (server.get("tools") or {}).get("include")
    required_tools = set(json.loads(MCP_TOOL_SNAPSHOT.read_text(encoding="utf-8")))
    # Omitting include is intentional: the server itself owns the public tool
    # snapshot. If an explicit include list exists, it must match that snapshot
    # rather than a separately maintained hand-written copy.
    included_tools = set(include_value or []) if include_value is not None else required_tools
    if included_tools != required_tools:
        errors.append(
            f"xiaoxue-product 工具白名单不一致：缺少 {sorted(required_tools - included_tools)}，"
            f"多出 {sorted(included_tools - required_tools)}"
        )
    if not mcp_target.is_file():
        errors.append(f"MCP 候选不存在：{mcp_target}")

    feishu_tools = set(((config.get("platform_toolsets") or {}).get("feishu") or []))
    if "xiaoxue-product" not in feishu_tools:
        errors.append("飞书没有启用 xiaoxue-product")
    if "no_mcp" in feishu_tools:
        errors.append("飞书仍被 no_mcp 禁止加载产品工具")
    enabled_plugins = set(((config.get("plugins") or {}).get("enabled") or []))
    boundary_plugin = PRODUCT_BOUNDARY_PLUGIN / "__init__.py"
    boundary_manifest = PRODUCT_BOUNDARY_PLUGIN / "plugin.yaml"
    if "xiaoxue-product-boundary" not in enabled_plugins:
        errors.append("飞书通用能力缺少 xiaoxue-product-boundary 一次性审批边界")
    if not boundary_manifest.is_file():
        errors.append(f"产品边界插件清单不存在：{boundary_manifest}")
    if boundary_plugin.is_file():
        boundary_source = boundary_plugin.read_text(encoding="utf-8", errors="replace")
        if 'ctx.register_hook("pre_tool_call"' not in boundary_source:
            errors.append("产品边界插件没有注册 pre_tool_call 审批钩子")
        if '"action": "approve"' not in boundary_source:
            errors.append("产品边界插件没有使用 Hermes 的一次性审批动作")
    else:
        errors.append(f"产品边界插件实现不存在：{boundary_plugin}")

    tool_search = ((config.get("tools") or {}).get("tool_search") or {})
    if str(tool_search.get("enabled", "")).lower() not in {"off", "false", "0"}:
        errors.append("xiaoxue-product 仍会被延迟工具搜索隐藏")

    channels = ((config.get("channels") or {}).get("feishu") or {})
    display = (((config.get("display") or {}).get("platforms") or {}).get("feishu") or {})
    platform = ((config.get("platforms") or {}).get("feishu") or {})
    if channels.get("streaming") is not True or display.get("streaming") is not True:
        errors.append("飞书流式开关没有在通道层和显示层同时开启")
    if platform.get("batch_delay") != 0:
        errors.append("飞书 batch_delay 不是 0")

    disabled = set((((config.get("skills") or {}).get("platform_disabled") or {}).get("feishu") or []))
    missing_disabled = REQUIRED_DISABLED_SKILLS - disabled
    wrongly_disabled = REQUIRED_ENABLED_SKILLS & disabled
    if missing_disabled:
        errors.append(f"重叠/旧入口仍在飞书候选中：{sorted(missing_disabled)}")
    if wrongly_disabled:
        errors.append(f"小雪正式入口被误禁用：{sorted(wrongly_disabled)}")
    enabled_count = len(_skill_names() - disabled)
    if enabled_count > 70:
        errors.append(f"飞书仍暴露过多 Skill：{enabled_count} 个")
    return errors


def _check_runtime_docs(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        files = [path] if path.is_file() else list(path.rglob("*.md"))
        for file_path in files:
            if any(part.startswith(".bak") or ".bak" in part for part in file_path.parts):
                continue
            text = file_path.read_text(encoding="utf-8", errors="replace")
            for marker in RETIRED_RUNTIME_MARKERS:
                if marker in text:
                    errors.append(f"仍引用废弃入口 {marker}: {file_path}")
    return errors


def _check_root_route(root_skill: Path) -> list[str]:
    text = root_skill.read_text(encoding="utf-8")
    errors = []
    for token in ("lol-competition-basics", "xiaoxue_remember"):
        if token not in text:
            errors.append(f"小雪根入口缺少确定性路由：{token}")
    tk_norms = (
        ("普通聊天", "提到 TK", "不自动保存"),
        ("明确要求", "写进 TK", "才写入"),
    )
    for markers in tk_norms:
        if not all(marker in text for marker in markers):
            errors.append("小雪根入口的 TK 持久化边界不完整：" + " / ".join(markers))
    return errors


def _check_api(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/openapi.json", timeout=8) as response:
            data = json.load(response)
    except Exception as exc:
        return [f"无法读取小雪 OpenAPI：{exc}"]
    paths = set((data.get("paths") or {}).keys())
    missing = REQUIRED_API_PATHS - paths
    return [f"小雪正式 API 缺失：{sorted(missing)}"] if missing else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--api-base", default="http://127.0.0.1:8880")
    args = parser.parse_args()

    try:
        targets, runtime_docs = _load_package(args.package)
        errors = []
        errors.extend(_check_config(_load_yaml(targets["hermes-config"]), targets["xiaoxue-product-mcp"]))
        errors.extend(_check_runtime_docs(runtime_docs))
        errors.extend(_check_root_route(targets["xiaoxue-root"]))
        errors.extend(_check_api(args.api_base))
    except Exception as exc:
        errors = [str(exc)]

    result = {"ok": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
