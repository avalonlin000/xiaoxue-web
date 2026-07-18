"""Deterministic contracts shared by Xiaoxue fixed workflows."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


def load_workflow_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if data.get("schema") != "xiaoxue-workflows-v1":
        raise ValueError("unsupported Xiaoxue workflow config schema")
    return data


def build_daily_content_files(config: dict[str, Any], date_str: str) -> dict[str, dict[str, str]]:
    daily = config.get("daily_content") or {}
    roots = [Path(value).resolve() for value in daily.get("allowed_roots") or []]
    files: dict[str, dict[str, str]] = {}
    for artifact in daily.get("artifacts") or []:
        path = Path(str(artifact["path"]).format(date=date_str)).resolve()
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError(f"daily artifact escapes allowed roots: {path}")
        artifact_id = str(artifact["id"])
        files[artifact_id] = {
            "title": str(artifact["title"]).format(date=date_str),
            "kind": str(artifact.get("kind") or artifact_id),
            "path": str(path),
        }
    return files


def build_team_alias_lookup(config: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in (config.get("team_aliases") or {}).items():
        for alias in [canonical, *(aliases or [])]:
            value = str(alias).strip()
            if value:
                lookup[value.casefold()] = str(canonical).strip().upper()
    return lookup


def prepare_lineup_workflow(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    lineup_config = config.get("lineup_workflow") or {}
    positions = lineup_config.get("positions") or ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]
    missing: list[str] = []
    for field in ["match_name", "blue_team", "red_team"]:
        if not str(payload.get(field) or "").strip():
            missing.append(field)
    for side in ["blue_lineup", "red_lineup"]:
        lineup = payload.get(side) or {}
        for position in positions:
            if not str(lineup.get(position) or "").strip():
                missing.append(f"{side}.{position}")
    return {
        "schema": "xiaoxue-lineup-workflow-v1",
        "ready": not missing,
        "missing_fields": missing,
        "steps": lineup_config.get("steps") or [],
        "allowed_decisions": lineup_config.get("allowed_decisions") or [],
        "guardrails": str(lineup_config.get("guardrails") or ""),
    }


def build_market_note_review(
    note: dict[str, Any], payload: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    review_config = config.get("market_review_workflow") or {}
    valid_results = set((config.get("market") or {}).get("results") or [])
    result = str(payload.get("result") or "未结算").strip()
    if result not in valid_results:
        raise ValueError(f"invalid market-note result: {result}")
    allowed_destinations = set(review_config.get("destinations") or [])
    destinations = [str(value) for value in payload.get("destinations") or []]
    invalid = [value for value in destinations if value not in allowed_destinations]
    if invalid:
        raise ValueError(f"invalid review destinations: {', '.join(invalid)}")

    start = str(review_config.get("managed_start") or "XIAOXUE_REVIEW_START")
    end = str(review_config.get("managed_end") or "XIAOXUE_REVIEW_END")
    original = str(note.get("review") or "")
    original = re.sub(rf"\n?<!-- {re.escape(start)} -->.*?<!-- {re.escape(end)} -->", "", original, flags=re.S)
    original_lines = [line for line in original.splitlines() if not line.strip().startswith("结果：")]
    original = "\n".join(original_lines).strip()
    managed = [
        f"<!-- {start} -->",
        "【赛后复盘】",
        f"结果：{result}",
        f"实际比分：{str(payload.get('actual_score') or '待补').strip()}",
        f"实际 BP/阵容：{str(payload.get('actual_lineup') or '待补').strip()}",
        f"关键转折：{str(payload.get('key_turns') or '待补').strip()}",
        f"判断正确点：{str(payload.get('correct_points') or '待补').strip()}",
        f"判断错误点：{str(payload.get('wrong_points') or '待补').strip()}",
        f"缺失证据：{str(payload.get('missing_evidence') or '待补').strip()}",
        f"校准结论：{str(payload.get('calibration') or '待确认').strip()}",
        f"建议沉淀：{', '.join(destinations) if destinations else '仅 market_notes'}",
        f"<!-- {end} -->",
    ]
    text = "\n".join([f"结果：{result}", original, "\n".join(managed)]).strip()
    return {
        "schema": "xiaoxue-market-review-v1",
        "note_id": note.get("id"),
        "review_text": text,
        "destinations": destinations,
        "knowledge_write_allowed": bool(review_config.get("knowledge_write_allowed", False)),
    }
