"""Deterministic trade-plan storage compatibility and composition; no I/O or inference."""
from __future__ import annotations

import json
import uuid


PLAN_MARKETS = {
    "team": {"label": "队伍", "directions": {"做多", "做空"}},
    "kills": {"label": "人头", "directions": {"做大", "做小"}},
    "duration": {"label": "时间", "directions": {"做大", "做小"}},
}


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _auto_trade_plan_from_storage(value) -> dict:
    raw = _json_object(value)
    if isinstance(raw.get("items"), list):
        return {"items": [item for item in raw["items"] if isinstance(item, dict)]}
    # First-slice compatibility: preserve existing category arrays as automatic items.
    items: list[dict] = []
    for market in PLAN_MARKETS:
        for index, legacy in enumerate(raw.get(market) or []):
            if not isinstance(legacy, dict):
                continue
            source_statement = str(legacy.get("statement") or "")
            item_id = f"auto-legacy-{market}-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, source_statement or str(index)).hex[:12]}"
            items.append({
                "id": item_id, "origin": "auto", "market": market, "team": str(legacy.get("team") or ""),
                "direction": str(legacy.get("direction") or ""), "statement": source_statement,
                "source": {"tk_id": "", "statement": source_statement, "scope_label": "交易 TK", "updated_at": ""},
            })
    return {"items": items}


def _empty_manual_trade_plan() -> dict:
    return {"items": [], "overrides": {}, "order": []}


def _manual_trade_plan(value) -> dict:
    raw = _json_object(value)
    manual = _empty_manual_trade_plan()
    if isinstance(raw.get("items"), list):
        manual["items"] = [item for item in raw["items"] if isinstance(item, dict) and str(item.get("id") or "")]
    else:
        # Preserve first-slice manual entries while converting them into normal item rows.
        for market in PLAN_MARKETS:
            for index, legacy in enumerate(raw.get(market) or []):
                if not isinstance(legacy, dict):
                    continue
                manual["items"].append({
                    "id": f"manual-legacy-{market}-{index}", "origin": "manual", "market": market,
                    "team": str(legacy.get("team") or ""), "direction": str(legacy.get("direction") or ""),
                    "statement": str(legacy.get("statement") or ""), "source": {},
                })
        for index, note in enumerate(raw.get("notes") or []):
            manual["items"].append({
                "id": f"manual-legacy-note-{index}", "origin": "manual", "market": "note", "team": "",
                "direction": "", "statement": str(note or ""), "source": {},
            })
    if isinstance(raw.get("overrides"), dict):
        manual["overrides"] = {str(key): value for key, value in raw["overrides"].items() if isinstance(value, dict)}
    if isinstance(raw.get("order"), list):
        manual["order"] = [str(value) for value in raw["order"] if str(value)]
    return manual


def _frozen_trade_plan(value: dict) -> dict:
    raw = _json_object(value)
    if "auto" in raw or "manual" in raw:
        auto = _auto_trade_plan_from_storage(raw.get("auto"))
        manual = _manual_trade_plan(raw.get("manual"))
        final = raw.get("final") if isinstance(raw.get("final"), dict) else _compose_trade_plan(auto, manual)
        if not isinstance(final.get("items"), list):
            final = _compose_trade_plan(auto, manual)
        return {"auto": auto, "manual": manual, "final": final, "frozen_at": str(raw.get("frozen_at") or ""), "snapshot_missing": bool(raw.get("snapshot_missing"))}
    # Old frozen rows stored only the final category arrays.
    auto = _auto_trade_plan_from_storage(raw)
    manual = _empty_manual_trade_plan()
    return {"auto": auto, "manual": manual, "final": _compose_trade_plan(auto, manual), "frozen_at": ""}


def _compose_trade_plan(auto: dict, manual: dict) -> dict:
    effective: list[dict] = []
    for base in auto.get("items") or []:
        override = manual.get("overrides", {}).get(base.get("id"), {})
        if override.get("mode") == "delete":
            continue
        item = dict(override.get("item") or base) if override.get("mode") == "replace" else dict(base)
        item["origin"] = "auto"
        item["source"] = dict(base.get("source") or item.get("source") or {})
        effective.append(item)
    effective.extend(dict(item) for item in manual.get("items") or [])
    order = _ordered_ids(effective, manual.get("order") or [])
    positions = {item_id: index for index, item_id in enumerate(order)}
    effective.sort(key=lambda item: positions.get(item.get("id"), len(positions)))
    for index, item in enumerate(effective, start=1):
        item["position"] = index
    grouped = {market: [item for item in effective if item.get("market") == market] for market in PLAN_MARKETS}
    return {"items": effective, **grouped}


def _ordered_ids(items: list[dict], saved_order: list[str]) -> list[str]:
    current_ids = [str(item.get("id") or "") for item in items if str(item.get("id") or "")]
    order = [item_id for item_id in saved_order if item_id in current_ids]
    order.extend(item_id for item_id in current_ids if item_id not in order)
    return order
