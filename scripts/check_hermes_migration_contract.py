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
    "/api/team-trading-notes",
    "/api/team-trading-notes/{team}",
    "/api/market-notes",
    "/api/current-event/match-run/active",
    "/api/current-event/match-run/pause",
    "/api/current-event/match-run/entry",
    "/api/current-event/match-run/candidates",
    "/api/stage-review/candidates",
    "/api/stage-review/candidates/{candidate_id}",
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
REQUIRED_MCP_TOOLS = {
    "xiaoxue_get_today",
    "xiaoxue_find_schedules",
    "xiaoxue_search_external_news",
    "xiaoxue_start_match_run",
    "xiaoxue_get_match_run",
    "xiaoxue_get_active_match_trade",
    "xiaoxue_pause_match_trade",
    "xiaoxue_save_match_trade_entry",
    "xiaoxue_update_match_run_fact",
    "xiaoxue_get_score_evidence",
    "xiaoxue_debug_reveal_match_result",
    "xiaoxue_get_match_run_review",
    "xiaoxue_add_stage_candidate",
    "xiaoxue_list_stage_candidates",
    "xiaoxue_update_stage_candidate",

    "xiaoxue_search_trading_tk",

    "xiaoxue_get_match_workspace",
    "xiaoxue_save_match_workspace",
    "xiaoxue_record_match_change",
    "xiaoxue_get_team",
    "xiaoxue_get_match_research_brief",
    "xiaoxue_open_research_subject",
    "xiaoxue_list_research_subjects",
    "xiaoxue_get_research_subject",
    "xiaoxue_record_research_event",
    "xiaoxue_record_research_digest",
    "xiaoxue_record_research_review",
    "xiaoxue_record_research_material",
    "xiaoxue_record_research_note",
    "xiaoxue_search_tk",
    "xiaoxue_get_tk_entry",
    "xiaoxue_list_market_notes",

}
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
    for skill_file in Path("/home/ubuntu/.agents/skills").glob("*/SKILL.md"):
        text = skill_file.read_text(encoding="utf-8", errors="replace")[:4000]
        match = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
        if match:
            names.add(match.group(1).strip())
    return names


def _check_config(config: dict[str, Any], mcp_target: Path) -> list[str]:
    errors: list[str] = []
    server = (config.get("mcp_servers") or {}).get("xiaoxue-product") or {}
    expected_command = "/home/ubuntu/.hermes/hermes-agent/venv/bin/python"
    expected_script = "/home/ubuntu/xiaoxue-web/scripts/hermes/xiaoxue_product_mcp.py"
    if server.get("command") != expected_command:
        errors.append("xiaoxue-product MCP 没有使用 Hermes Python")
    if expected_script not in (server.get("args") or []):
        errors.append("xiaoxue-product MCP 没有指向小雪正式适配器")
    included_tools = set(((server.get("tools") or {}).get("include") or []))
    if included_tools != REQUIRED_MCP_TOOLS:
        errors.append(f"xiaoxue-product 工具白名单不完整：{sorted(included_tools)}")
    if not mcp_target.is_file():
        errors.append(f"MCP 候选不存在：{mcp_target}")

    feishu_tools = set(((config.get("platform_toolsets") or {}).get("feishu") or []))
    if "xiaoxue-product" not in feishu_tools:
        errors.append("飞书没有启用 xiaoxue-product")
    if "no_mcp" in feishu_tools:
        errors.append("飞书仍被 no_mcp 禁止加载产品工具")
    forbidden_generic = {"terminal", "file"} & feishu_tools
    if forbidden_generic:
        errors.append(f"飞书仍暴露可退回旧路径的通用工具：{sorted(forbidden_generic)}")

    tool_search = ((config.get("tools") or {}).get("tool_search") or {})
    if str(tool_search.get("enabled", "")).lower() not in {"off", "false", "0"}:
        errors.append("xiaoxue-product 仍会被延迟工具搜索隐藏")

    platform_hint = str((((config.get("platform_hints") or {}).get("feishu") or {}).get("append") or ""))
    for marker in (
        "never use terminal, file, read_file, search_files, or shell",
        "xiaoxue_get_today",
        "xiaoxue_search_external_news",
        "call it exactly once",
        "without a generic-tool fallback",
    ):
        if marker not in platform_hint:
            errors.append(f"飞书平台路由提示缺少强制约束：{marker}")

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
    for token in ("lol-competition-basics", "明确提到“TK”", "xiaoxue_remember"):
        if token not in text:
            errors.append(f"小雪根入口缺少确定性路由：{token}")
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
