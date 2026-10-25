from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoxue_api.core.product_modules import module_by_id, module_catalog, object_catalog, project_root
from xiaoxue_api.modules.daily_content.public import get_daily_content
from xiaoxue_api.modules.platform.public import health

from . import repository


DEFAULT_DB_PATH = "/home/ubuntu/xiaoxue-web/data/project_center.sqlite3"
BASKET_STATUSES = {"pending", "paused", "transferred", "removed"}
LIFECYCLE_STATUSES = {"Planned", "In Progress", "Implemented", "Verified", "Released", "Blocked", "Abandoned"}
VISIBLE_LIFECYCLE = {
    "Planned": "方案中", "In Progress": "修改中", "Implemented": "待验证", "Verified": "已验证",
    "Released": "已发布", "Blocked": "阻塞", "Abandoned": "已归档",
}
MODULE_RUNTIME = {"healthy", "degraded", "paused", "disabled", "broken"}


class ProjectCenterError(ValueError):
    status_code = 400
    code = "invalid_project_center_input"


class NotFoundError(ProjectCenterError):
    status_code = 404
    code = "project_center_not_found"


class ConflictError(ProjectCenterError):
    status_code = 409
    code = "project_center_conflict"


def overview() -> dict[str, Any]:
    content = _content()
    observed_at = _now()
    runtime = _runtime_summary()
    daily = _daily_summary()
    deliveries = list_deliveries(limit=4)["data"]["items"]
    requests = list_requests(limit=4)["data"]["items"]
    status = "partial" if runtime["status"] != "healthy" or daily["status"] != "ready" else "ok"
    return _result(
        status,
        "项目目标、当前运行状态和处理进度已分开显示",
        {
            "project": content["project"],
            "book": content["book"],
            "object_catalog": object_catalog(),
            "runtime": runtime,
            "daily": daily,
            "current_requests": requests,
            "current_deliveries": deliveries,
            "source": "小雪当前运行状态与项目合同",
            "observed_at": observed_at,
            "content_version": content["content_version"],
            "stale": False,
        },
        gaps=[] if status == "ok" else ["部分运行状态或今日内容尚未就绪，已在页面中单独标出"],
    )


def list_modules() -> dict[str, Any]:
    content = _content()
    runtime_by_module = (_safe_health().get("modules") or {})
    catalog = {item["id"]: item for item in module_catalog()}
    modules = _group_user_modules([_public_module(item, content, runtime_by_module) for item in catalog.values()])
    tree = [_public_tree_node(node, content, catalog, runtime_by_module) for node in content["module_tree"]]
    return _result("ok", "已读取当前模块与实际入口", {
        "items": modules,
        "tree": tree,
        "object_catalog": object_catalog(),
        "source": "项目模块合同与当前运行状态",
        "observed_at": _now(),
        "content_version": content["content_version"],
        "stale": False,
    })


def get_module(module_id: str) -> dict[str, Any]:
    module = module_by_id(_clean_module_id(module_id))
    if not module:
        raise NotFoundError("没有找到这个项目模块")
    content = _content()
    item = _public_module(module, content, (_safe_health().get("modules") or {}))
    return _result("ok", "已读取模块快照", {"item": item, "source": "项目模块合同", "observed_at": _now(), "content_version": content["content_version"], "stale": False})


def get_manual() -> dict[str, Any]:
    content = _content()
    return _result("ok", "已读取当前使用说明", {"manual": content["manual"], "source": "当前产品说明", "observed_at": _now(), "content_version": content["content_version"], "stale": False})


def list_basket(status: str = "active", limit: int = 50) -> dict[str, Any]:
    with _connection() as connection:
        if connection is None:
            items: list[dict[str, Any]] = []
        else:
            where, params = _basket_filter(status, limit)
            items = repository.fetch_all(connection, f"SELECT * FROM basket_items WHERE {where} ORDER BY is_focus DESC, updated_at DESC LIMIT ?", (*params, limit))
    focus = next((item for item in items if item["is_focus"] and item["status"] in {"pending", "paused"}), None)
    return _result("empty" if not items else "ok", "待修改框已读取" if items else "待修改框还没有内容", {
        "items": items,
        "count": len(items),
        "focus": focus,
        "source": "项目中心待修改框",
        "observed_at": _now(),
        "content_version": _content()["content_version"],
        "stale": False,
    })


def create_basket_item(values: dict[str, Any]) -> dict[str, Any]:
    owner = _clean_text(values.get("owner") or "钧钧", "归属", maximum=80)
    module_id = _clean_optional_module_id(values.get("module_id"))
    note = _clean_text(values.get("optional_note") or "", "备注", maximum=600, required=False)
    if not module_id and not note:
        raise ProjectCenterError("请至少留下一句想讨论的感觉")
    content = _content()
    snapshot = _snapshot_for(module_id, content)
    if not module_id:
        snapshot = {"module_name": "还没找到模块的想法", "purpose": "先保留这句感受，讨论时再归类", "entry": {"type": "chat", "label": "在飞书和小白聊聊"}}
    item_id = f"basket-{uuid.uuid4().hex[:12]}"
    now = _now()
    payload = {"module_id": module_id or "unassigned", "optional_note": note, "owner": owner}
    with _connection(writable=True) as connection:
        if connection is None:
            raise ProjectCenterError("待修改暂时无法保存")
        deduped = _dedupe_or_none(connection, "basket.create", values.get("idempotency_key"), payload)
        if deduped:
            return _result("ok", "这条待修改已经在框里了", {"item": _get_or_not_found(connection, "basket_items", deduped["entity_id"]), "deduplicated": True, "readback": True})
        if module_id:
            existing = repository.fetch_one(
                connection,
                "SELECT * FROM basket_items WHERE owner=? AND module_id=? AND status IN ('pending', 'paused') ORDER BY updated_at DESC LIMIT 1",
                (owner, module_id),
            )
            if existing:
                return _result("ok", "这个模块已经在待修改里了", {"item": existing, "deduplicated": True, "readback": True})
            connection.execute("UPDATE basket_items SET is_focus=0 WHERE is_focus=1 AND status IN ('pending', 'paused')")
        item = {
            "id": item_id, "created_at": now, "updated_at": now, "owner": owner,
            "module_id": module_id or "unassigned", "module_name": snapshot["module_name"],
            "optional_note": note, "status": "pending", "is_focus": 1 if module_id else 0,
            "context_snapshot": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), "revision": 1, "archived_at": None,
        }
        repository.insert(connection, "basket_items", item)
        repository.record_event(connection, entity_type="basket", entity_id=item_id, occurred_at=now, owner=owner, event_type="created", after={"status": "pending"})
        _save_idempotency(connection, "basket.create", values.get("idempotency_key"), "basket", item_id, payload, now)
        readback = _get_or_not_found(connection, "basket_items", item_id)
    return _result("ok", "已加入待修改，之后可以在飞书说“聊聊待修改”", {"item": readback, "readback": True})


def update_basket_item(item_id: str, values: dict[str, Any]) -> dict[str, Any]:
    desired_status = values.get("status")
    if desired_status is not None and desired_status not in BASKET_STATUSES:
        raise ProjectCenterError("待修改状态不正确")
    revision = _revision(values.get("revision"))
    owner = _clean_text(values.get("owner") or "钧钧", "归属", maximum=80)
    with _connection(writable=True) as connection:
        current = _get_or_not_found(connection, "basket_items", item_id)
        changes: dict[str, Any] = {"updated_at": _now()}
        if desired_status is not None:
            changes["status"] = desired_status
            if desired_status == "removed":
                changes["archived_at"] = changes["updated_at"]
                changes["is_focus"] = 0
        if "is_focus" in values:
            is_focus = bool(values["is_focus"])
            if is_focus and desired_status == "removed":
                raise ProjectCenterError("已移除的条目不能设为当前焦点")
            if is_focus:
                connection.execute("UPDATE basket_items SET is_focus=0 WHERE is_focus=1 AND id<>?", (item_id,))
            changes["is_focus"] = int(is_focus)
        if not repository.update(connection, "basket_items", item_id, revision, changes):
            raise ConflictError("这条待修改刚被更新，请刷新后再试")
        updated = _get_or_not_found(connection, "basket_items", item_id)
        repository.record_event(connection, entity_type="basket", entity_id=item_id, occurred_at=changes["updated_at"], owner=owner, event_type="updated", before={"status": current["status"]}, after={"status": updated["status"]})
    return _result("ok", "待修改已更新", {"item": updated, "readback": True})


def list_requests(status: str = "active", limit: int = 50) -> dict[str, Any]:
    with _connection() as connection:
        items = [] if connection is None else repository.fetch_all(connection, f"SELECT * FROM change_requests WHERE {_lifecycle_filter(status)} ORDER BY updated_at DESC LIMIT ?", (limit,))
    return _result("empty" if not items else "ok", "正式处理事项已读取" if items else "暂时没有已进入处理的事项", {"items": [_request_summary(item) for item in items], "source": "项目中心处理事项", "observed_at": _now(), "stale": False})


def get_request(request_id: str) -> dict[str, Any]:
    with _connection() as connection:
        if connection is None:
            raise NotFoundError("没有找到这个处理事项")
        item = _get_or_not_found(connection, "change_requests", request_id)
        deliveries = repository.fetch_all(connection, "SELECT * FROM deliveries WHERE request_id=? ORDER BY updated_at DESC", (request_id,))
    return _result("ok", "已读取处理事项和关联交付", {"item": item, "deliveries": deliveries, "readback": True})


def create_request(values: dict[str, Any]) -> dict[str, Any]:
    if values.get("discussion_confirmed") is not True:
        raise ProjectCenterError("正式处理事项要在飞书讨论并确认目标后再创建")
    basket_ids = _ids(values.get("basket_item_ids"), "待修改条目")
    owner = _clean_text(values.get("owner") or "小白", "归属", maximum=80)
    user_problem = _clean_text(values.get("user_problem"), "原始感受", maximum=1200)
    desired_experience = _clean_text(values.get("desired_experience"), "期望体验", maximum=1200)
    desired_result = _clean_text(values.get("desired_result"), "预期结果", maximum=1200)
    notes = _clean_text(values.get("notes") or "", "补充说明", maximum=2400, required=False)
    now = _now()
    request_id = f"request-{uuid.uuid4().hex[:12]}"
    payload = {"basket_item_ids": basket_ids, "user_problem": user_problem, "desired_experience": desired_experience, "desired_result": desired_result}
    with _connection(writable=True) as connection:
        deduped = _dedupe_or_none(connection, "request.create", values.get("idempotency_key"), payload)
        if deduped:
            return _result("ok", "这个处理事项已经创建过", {"item": _get_or_not_found(connection, "change_requests", deduped["entity_id"]), "deduplicated": True, "readback": True})
        basket_items = [_get_or_not_found(connection, "basket_items", item_id) for item_id in basket_ids]
        if any(item["status"] not in {"pending", "paused"} for item in basket_items):
            raise ConflictError("待修改里有条目已被转为处理或移除，请刷新后再试")
        primary = basket_items[0]
        request = {
            "id": request_id, "created_at": now, "updated_at": now, "owner": owner,
            "module_id": primary["module_id"], "module_name": primary["module_name"],
            "basket_item_ids": json.dumps(basket_ids, ensure_ascii=False), "user_problem": user_problem,
            "desired_experience": desired_experience, "desired_result": desired_result, "notes": notes,
            "status": "Planned", "triage_summary": _clean_text(values.get("triage_summary") or "", "处理摘要", maximum=2400, required=False),
            "impact_summary": _clean_text(values.get("impact_summary") or "", "影响说明", maximum=2400, required=False),
            "locked_decisions": _clean_text(values.get("locked_decisions") or "", "已定决定", maximum=2400, required=False),
            "delivery_summary": "", "verification_summary": "", "user_validation_path": "", "blockers": "", "archived_reason": "",
            "revision": 1, "archived_at": None,
        }
        repository.insert(connection, "change_requests", request)
        for item in basket_items:
            repository.update(connection, "basket_items", item["id"], item["revision"], {"status": "transferred", "is_focus": 0, "updated_at": now})
        repository.record_event(connection, entity_type="request", entity_id=request_id, occurred_at=now, owner=owner, event_type="created_after_discussion", after={"status": "Planned", "basket_item_ids": basket_ids})
        _save_idempotency(connection, "request.create", values.get("idempotency_key"), "request", request_id, payload, now)
        readback = _get_or_not_found(connection, "change_requests", request_id)
    return _result("ok", "已转为正式处理事项", {"item": readback, "readback": True})


def update_request(request_id: str, values: dict[str, Any]) -> dict[str, Any]:
    revision = _revision(values.get("revision"))
    owner = _clean_text(values.get("owner") or "小白", "归属", maximum=80)
    with _connection(writable=True) as connection:
        current = _get_or_not_found(connection, "change_requests", request_id)
        changes = _request_changes(values, current)
        changes["updated_at"] = _now()
        if not repository.update(connection, "change_requests", request_id, revision, changes):
            raise ConflictError("这条处理事项刚被更新，请刷新后再试")
        updated = _get_or_not_found(connection, "change_requests", request_id)
        repository.record_event(connection, entity_type="request", entity_id=request_id, occurred_at=changes["updated_at"], owner=owner, event_type="updated", before={"status": current["status"]}, after={"status": updated["status"]})
    return _result("ok", "处理事项已更新", {"item": updated, "readback": True})


def list_deliveries(status: str = "active", limit: int = 50) -> dict[str, Any]:
    with _connection() as connection:
        items = [] if connection is None else repository.fetch_all(connection, f"SELECT * FROM deliveries WHERE {_lifecycle_filter(status)} ORDER BY updated_at DESC LIMIT ?", (limit,))
    return _result("empty" if not items else "ok", "当前交付已读取" if items else "还没有可展示的交付", {"items": [_delivery_summary(item) for item in items], "source": "项目中心交付记录", "observed_at": _now(), "stale": False})


def get_delivery(delivery_id: str) -> dict[str, Any]:
    with _connection() as connection:
        if connection is None:
            raise NotFoundError("没有找到这个交付")
        item = _get_or_not_found(connection, "deliveries", delivery_id)
    return _result("ok", "已读取交付", {"item": item, "readback": True})


def create_delivery(values: dict[str, Any]) -> dict[str, Any]:
    owner = _clean_text(values.get("owner") or "小白", "归属", maximum=80)
    title = _clean_text(values.get("title"), "交付标题", maximum=200)
    status = _lifecycle(values.get("status") or "Implemented")
    evidence = _evidence(values.get("verification_evidence") or [])
    if status == "Verified" and not evidence:
        raise ProjectCenterError("标为已验证时需要至少一条可理解的验证结果")
    request_id = _clean_text(values.get("request_id") or "", "处理事项", maximum=80, required=False)
    now = _now()
    delivery_id = f"delivery-{uuid.uuid4().hex[:12]}"
    payload = {"title": title, "status": status, "request_id": request_id}
    with _connection(writable=True) as connection:
        deduped = _dedupe_or_none(connection, "delivery.create", values.get("idempotency_key"), payload)
        if deduped:
            return _result("ok", "这个交付已经创建过", {"item": _get_or_not_found(connection, "deliveries", deduped["entity_id"]), "deduplicated": True, "readback": True})
        if request_id:
            _get_or_not_found(connection, "change_requests", request_id)
        item = {
            "id": delivery_id, "created_at": now, "updated_at": now, "owner": owner, "request_id": request_id or None,
            "title": title, "status": status, "user_visible_change": _clean_text(values.get("user_visible_change"), "可感知变化", maximum=2400),
            "verification_evidence": json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
            "known_risks": _clean_text(values.get("known_risks") or "", "当前风险", maximum=1600, required=False),
            "user_validation_path": _clean_text(values.get("user_validation_path") or "", "体验入口", maximum=800, required=False),
            "published_at": now if status == "Released" else None, "feedback_action": "", "feedback_note": "", "revision": 1, "archived_at": None,
        }
        repository.insert(connection, "deliveries", item)
        repository.record_event(connection, entity_type="delivery", entity_id=delivery_id, occurred_at=now, owner=owner, event_type="created", after={"status": status})
        _save_idempotency(connection, "delivery.create", values.get("idempotency_key"), "delivery", delivery_id, payload, now)
        readback = _get_or_not_found(connection, "deliveries", delivery_id)
    return _result("ok", "交付已记录", {"item": readback, "readback": True})


def update_delivery(delivery_id: str, values: dict[str, Any]) -> dict[str, Any]:
    revision = _revision(values.get("revision"))
    owner = _clean_text(values.get("owner") or "钧钧", "归属", maximum=80)
    with _connection(writable=True) as connection:
        current = _get_or_not_found(connection, "deliveries", delivery_id)
        changes = _delivery_changes(values, current)
        changes["updated_at"] = _now()
        feedback_action = values.get("feedback_action")
        if feedback_action == "return_to_basket":
            _return_delivery_to_basket(connection, current, values, owner, changes["updated_at"])
            changes["status"] = "Abandoned"
            changes["archived_at"] = changes["updated_at"]
        elif feedback_action == "archive":
            changes["status"] = "Abandoned"
            changes["archived_at"] = changes["updated_at"]
        if not repository.update(connection, "deliveries", delivery_id, revision, changes):
            raise ConflictError("这个交付刚被更新，请刷新后再试")
        updated = _get_or_not_found(connection, "deliveries", delivery_id)
        repository.record_event(connection, entity_type="delivery", entity_id=delivery_id, occurred_at=changes["updated_at"], owner=owner, event_type="feedback" if feedback_action else "updated", before={"status": current["status"]}, after={"status": updated["status"], "feedback_action": feedback_action or ""})
    summary = "已归档这次体验" if feedback_action == "archive" else "已放回待修改，等你和小白换一种做法" if feedback_action == "return_to_basket" else "交付已更新"
    return _result("ok", summary, {"item": updated, "readback": True})


def _request_changes(values: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    allowed = {"triage_summary": 2400, "impact_summary": 2400, "locked_decisions": 2400, "delivery_summary": 2400, "verification_summary": 2400, "user_validation_path": 800, "blockers": 1600, "archived_reason": 1600, "notes": 2400}
    changes = {field: _clean_text(values[field], field, maximum=maximum, required=False) for field, maximum in allowed.items() if field in values}
    if "status" in values:
        status = _lifecycle(values["status"])
        if status == "Verified" and not (changes.get("verification_summary") or current.get("verification_summary")):
            raise ProjectCenterError("标为已验证时请写清已观察到的验证结果")
        changes["status"] = status
        if status == "Abandoned":
            changes["archived_at"] = _now()
    return changes


def _delivery_changes(values: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "status" in values:
        status = _lifecycle(values["status"])
        evidence = _evidence(values.get("verification_evidence", current["verification_evidence"]))
        if status == "Verified" and not evidence:
            raise ProjectCenterError("标为已验证时需要至少一条可理解的验证结果")
        changes["status"] = status
        if status == "Released" and not current.get("published_at"):
            changes["published_at"] = _now()
    for field, maximum in (("title", 200), ("user_visible_change", 2400), ("known_risks", 1600), ("user_validation_path", 800), ("feedback_note", 1200)):
        if field in values:
            changes[field] = _clean_text(values[field], field, maximum=maximum, required=field in {"title", "user_visible_change"})
    if "verification_evidence" in values:
        changes["verification_evidence"] = json.dumps(_evidence(values["verification_evidence"]), ensure_ascii=False, separators=(",", ":"))
    feedback_action = values.get("feedback_action")
    if feedback_action not in {None, "", "archive", "return_to_basket"}:
        raise ProjectCenterError("体验反馈不正确")
    if feedback_action:
        changes["feedback_action"] = feedback_action
    return changes


def _return_delivery_to_basket(connection: sqlite3.Connection, delivery: dict[str, Any], values: dict[str, Any], owner: str, now: str) -> None:
    request = _get_or_none(connection, "change_requests", delivery.get("request_id") or "")
    module_id = request.get("module_id") if request else "unassigned"
    snapshot = _snapshot_for(module_id, _content()) if module_id != "unassigned" else {"module_name": "想换一种做法", "purpose": "已发布体验仍不符合预期", "entry": {"type": "chat", "label": "在飞书和小白聊聊"}}
    note = _clean_text(values.get("feedback_note") or "想换一种做法", "反馈", maximum=1200)
    connection.execute("UPDATE basket_items SET is_focus=0 WHERE is_focus=1")
    item_id = f"basket-{uuid.uuid4().hex[:12]}"
    item = {
        "id": item_id, "created_at": now, "updated_at": now, "owner": owner, "module_id": module_id,
        "module_name": snapshot["module_name"], "optional_note": f"关于“{delivery['title']}”：{note}", "status": "pending", "is_focus": 1,
        "context_snapshot": json.dumps({**snapshot, "previous_delivery": {"title": delivery["title"], "before": "原交付已发布", "now": "希望换一种体验"}}, ensure_ascii=False, separators=(",", ":")),
        "revision": 1, "archived_at": None,
    }
    repository.insert(connection, "basket_items", item)
    repository.record_event(connection, entity_type="basket", entity_id=item_id, occurred_at=now, owner=owner, event_type="returned_from_delivery", after={"delivery_id": delivery["id"]})


def _public_module(module: dict[str, Any], content: dict[str, Any], runtime_by_module: dict[str, Any]) -> dict[str, Any]:
    mapping = content["module_mapping"].get(module["id"], {})
    runtime_states = [runtime_by_module.get(capability, {}).get("status") for capability in module["compatibility"].get("backend_capabilities", [])]
    runtime = _module_runtime(runtime_states, module["status"])
    for capability in module["compatibility"].get("backend_capabilities", []):
        reason_code = runtime_by_module.get(capability, {}).get("reason_code")
        if reason_code == "readiness_missing":
            runtime["reason"] = "当天数据就绪信息缺失；不能据此确认日报产物或自动化执行成功"
        elif reason_code == "readiness_not_due":
            runtime["reason"] = "今天的数据按 05:30 自动刷新，现在还没到生成时点"
    entry = {
        "type": mapping.get("entry_type", "chat"), "label": mapping.get("entry_label", "在小雪对话使用"),
        "page": mapping.get("page", ""), "chat_prompt": mapping.get("chat_prompt", "聊聊这个模块"),
    }
    return {
        "id": module["id"], "name": mapping.get("module_name", module["display_name"]), "ability_name": module["display_name"],
        "purpose": mapping.get("user_purpose", module["purpose"]), "entry": entry, "runtime": runtime,
        "boundary": _user_boundary(module), "known_gap": module["read_capability"].get("empty", "资料不足时会明确提示"),
        "impact": module["consumers"], "next_step": _next_step(module, entry, runtime),
    }


def _public_tree_node(node: dict[str, Any], content: dict[str, Any], catalog: dict[str, dict[str, Any]], runtime_by_module: dict[str, Any]) -> dict[str, Any]:
    abilities = [_public_module(catalog[module_id], content, runtime_by_module) for module_id in node["ability_ids"]]
    entry = dict(node["entry"])
    entry.setdefault("type", "chat")
    entry.setdefault("label", "在小雪对话使用")
    entry.setdefault("page", "")
    entry.setdefault("chat_prompt", "聊聊这个模块")
    return {
        "id": node["id"],
        "name": node["name"],
        "purpose": node["purpose"],
        "when_to_use": node["when_to_use"],
        "current_capability": node["current_capability"],
        "entry": entry,
        "ability_ids": list(node["ability_ids"]),
        "ability_names": [ability["ability_name"] for ability in abilities],
        "runtime": _combined_runtime([ability["runtime"] for ability in abilities]),
        "runtime_details": [
            {"name": ability["ability_name"], **ability["runtime"]}
            for ability in abilities if ability["runtime"]["status"] != "healthy"
        ],
        "related_modules": list(node["related_modules"]),
        "boundaries": node["boundaries"],
        "known_gap": "；".join(dict.fromkeys(ability["known_gap"] for ability in abilities)),
        "next_step": node["next_step"],
        "basket_module_id": node["basket_module_id"],
        "engineering_details": dict(node["engineering_details"]),
        "group": node.get("group", ""),
        "children": [_public_tree_node(child, content, catalog, runtime_by_module) for child in node.get("children", [])],
    }
def _group_user_modules(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in items:
        grouped.setdefault(item["name"], []).append(item)
    return [_user_module_group(group) for group in grouped.values()]


def _user_module_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    primary = dict(items[0])
    primary["ability_ids"] = [item["id"] for item in items]
    primary["ability_names"] = [item["ability_name"] for item in items]
    primary["runtime"] = _combined_runtime([item["runtime"] for item in items])
    primary["boundary"] = "；".join(dict.fromkeys(item["boundary"] for item in items))
    primary["known_gap"] = "；".join(dict.fromkeys(item["known_gap"] for item in items))
    primary["impact"] = list(dict.fromkeys(value for item in items for value in item["impact"]))
    return primary


def _combined_runtime(items: list[dict[str, str]]) -> dict[str, str]:
    if not items:
        return _module_runtime([], "partial")
    priority = {"broken": 5, "degraded": 4, "paused": 3, "disabled": 2, "healthy": 1}
    return max(items, key=lambda item: priority.get(item.get("status", "degraded"), 4))


def _snapshot_for(module_id: str | None, content: dict[str, Any]) -> dict[str, Any]:
    module = module_by_id(module_id or "")
    if not module:
        return {"module_name": "还没找到模块的想法", "purpose": "先保留这句感受，讨论时再归类", "entry": {"type": "chat", "label": "在飞书和小白聊聊"}}
    public = _public_module(module, content, (_safe_health().get("modules") or {}))
    return {
        "module_name": public["name"],
        "purpose": public["purpose"],
        "entry": public["entry"],
        "runtime": public["runtime"],
        "known_gap": public["known_gap"],
        "impact": public["impact"],
    }


def _module_runtime(states: list[Any], contract_status: str) -> dict[str, str]:
    states = [state for state in states if state in MODULE_RUNTIME]
    contract_state = {"available": "healthy", "partial": "degraded", "blocked": "paused", "deprecated": "disabled"}.get(contract_status, "degraded")
    # A responding backend cannot promote a partially delivered capability.
    priority = {"healthy": 1, "disabled": 2, "paused": 3, "degraded": 4, "broken": 5}
    value = max([contract_state, *states], key=priority.__getitem__)
    labels = {"healthy": ("使用中", "当前入口正常"), "degraded": ("部分可用", "部分资料或环节仍有限制"), "paused": ("暂时暂停", "当前不把它作为日常入口"), "disabled": ("暂未启用", "目前不作为日常入口"), "broken": ("需要处理", "当前入口没有正常返回")}
    label, reason = labels[value]
    return {"status": value, "label": label, "reason": reason}


def _runtime_summary() -> dict[str, str]:
    payload = _safe_health()
    status = payload.get("status") if isinstance(payload, dict) else "broken"
    label = {"healthy": "整体可用", "degraded": "部分可用", "broken": "需要处理"}.get(status, "状态待确认")
    reason = "当前业务模块都已正常加载" if status == "healthy" else "有部分模块需要单独确认，不把它当作整个项目不可用"
    return {"status": status if status in {"healthy", "degraded", "broken"} else "degraded", "label": label, "reason": reason, "source": "小雪当前运行状态", "observed_at": _now(), "stale": False}


def _daily_summary() -> dict[str, Any]:
    report = {}
    try:
        payload = get_daily_content()
        state = str(payload.get("day_state") or "unknown")
        source_report = payload.get("report") or {}
        report = {key: source_report.get(key) for key in ("publication_status", "url", "snapshot_at")}
    except Exception:
        state = "unavailable"
    labels = {"ready": ("今天内容已就绪", "可以从日报开始"), "content_missing": ("今天内容还没齐", "需要等内容准备好或直接和小雪聊"), "no_matches": ("今天没有安排比赛", "可以查看已有资料或沉淀候选"), "unavailable": ("日报状态暂时读不到", "不影响其他入口继续使用")}
    label, reason = labels.get(state, ("日报状态待确认", "当前没有足够信息判断今天内容"))
    return {"status": state, "label": label, "reason": reason, "report": report, "source": "今日内容状态", "observed_at": _now(), "stale": state == "unavailable"}


def _user_boundary(module: dict[str, Any]) -> str:
    return module["analysis_capability"].get("boundary") or "资料不足时不替你补结论"


def _next_step(module: dict[str, Any], entry: dict[str, str], runtime: dict[str, str]) -> str:
    if runtime["status"] in {"broken", "degraded"}:
        return "先看看当前状态；觉得不顺就加入待修改"
    return entry["label"] if entry["type"] == "web" else "直接在小雪对话里使用"


def _request_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "status_label": VISIBLE_LIFECYCLE.get(item["status"], item["status"])}


def _delivery_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "status_label": VISIBLE_LIFECYCLE.get(item["status"], item["status"])}


def _safe_health() -> dict[str, Any]:
    try:
        return health()
    except Exception:
        return {"status": "broken", "modules": {}}


def _content() -> dict[str, Any]:
    path = project_root() / "config" / "project-center-content.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectCenterError("项目中心内容暂时不可读取") from exc
    return _validate_content(payload)


def _validate_content(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != "xiaoxue-project-center-content-v2":
        raise ProjectCenterError("项目中心内容版本不匹配")
    if not isinstance(payload.get("content_version"), str) or not isinstance(payload.get("content_schema"), dict):
        raise ProjectCenterError("项目中心内容缺少版本说明")
    if not isinstance(payload.get("project"), dict) or not isinstance(payload.get("book"), dict) or not isinstance(payload.get("manual"), dict):
        raise ProjectCenterError("项目中心内容结构不完整")
    book = payload["book"]
    chapters = book.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ProjectCenterError("项目开发书内容不完整")
    for chapter in chapters:
        _require_fields(chapter, ("id", "title", "summary", "paragraphs", "module_tree_ids"), "项目开发书章节")
        if not isinstance(chapter["paragraphs"], list) or not isinstance(chapter["module_tree_ids"], list):
            raise ProjectCenterError("项目开发书章节格式不正确")
    tree = payload.get("module_tree")
    if not isinstance(tree, list) or not tree:
        raise ProjectCenterError("开发模块树内容不完整")
    catalog_ids = {item["id"] for item in module_catalog()}
    tree_ids: set[str] = set()
    for node in tree:
        _validate_tree_node(node, catalog_ids, tree_ids, require_group=True)
    if not isinstance(payload["manual"].get("sections"), list) or not payload["manual"]["sections"]:
        raise ProjectCenterError("使用说明书内容不完整")
    for section in payload["manual"]["sections"]:
        _require_fields(section, ("id", "title", "what", "where", "say", "get", "not_for", "module_tree_id"), "使用说明场景")
        if not isinstance(section["say"], list) or section["module_tree_id"] not in tree_ids:
            raise ProjectCenterError("使用说明场景格式不正确")
    mappings = payload.get("module_mapping")
    if not isinstance(mappings, dict) or not catalog_ids.issubset(mappings):
        raise ProjectCenterError("项目中心模块映射不完整")
    return payload


def _validate_tree_node(node: object, catalog_ids: set[str], tree_ids: set[str], require_group: bool = False) -> None:
    if not isinstance(node, dict):
        raise ProjectCenterError("开发模块节点格式不正确")
    _require_fields(node, (
        "id", "name", "purpose", "when_to_use", "current_capability", "entry", "ability_ids",
        "related_modules", "boundaries", "next_step", "basket_module_id", "engineering_details",
    ), "开发模块节点")
    node_id = node["id"]
    if not isinstance(node_id, str) or not node_id or node_id in tree_ids:
        raise ProjectCenterError("开发模块节点 ID 缺失或重复")
    tree_ids.add(node_id)
    if not isinstance(node["entry"], dict) or not isinstance(node["engineering_details"], dict):
        raise ProjectCenterError("开发模块节点入口或工程说明不正确")
    group = node.get("group")
    if (require_group or group is not None) and group not in ("mainline", "foundation"):
        raise ProjectCenterError("开发模块缺少主线或底座分组")
    if not isinstance(node["ability_ids"], list) or not node["ability_ids"] or not set(node["ability_ids"]).issubset(catalog_ids):
        raise ProjectCenterError("开发模块节点引用了不存在的能力")
    if node["basket_module_id"] not in catalog_ids:
        raise ProjectCenterError("开发模块节点缺少待修改归属")
    if not isinstance(node["related_modules"], list):
        raise ProjectCenterError("开发模块节点关联说明不正确")
    children = node.get("children", [])
    if not isinstance(children, list):
        raise ProjectCenterError("开发模块子节点格式不正确")
    for child in children:
        _validate_tree_node(child, catalog_ids, tree_ids)


def _require_fields(value: object, fields: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict) or any(field not in value for field in fields):
        raise ProjectCenterError(f"{label}缺少必要内容")


@contextmanager
def _connection(*, writable: bool = False):
    path = Path(os.environ.get("XIAOXUE_PROJECT_CENTER_DB_PATH", DEFAULT_DB_PATH))
    if not writable and not path.exists():
        yield None
        return
    if writable:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        repository.initialize(connection)
        yield connection
        if writable:
            connection.commit()
    except Exception:
        if writable:
            connection.rollback()
        raise
    finally:
        connection.close()


def _get_or_not_found(connection: sqlite3.Connection, table: str, entity_id: str) -> dict[str, Any]:
    value = _get_or_none(connection, table, entity_id)
    if not value:
        raise NotFoundError("没有找到对应的项目中心记录")
    return value


def _get_or_none(connection: sqlite3.Connection, table: str, entity_id: str) -> dict[str, Any] | None:
    if not entity_id:
        return None
    return repository.fetch_one(connection, f"SELECT * FROM {table} WHERE id=?", (entity_id,))


def _basket_filter(status: str, limit: int) -> tuple[str, tuple[Any, ...]]:
    if status == "active":
        return "status IN ('pending', 'paused')", ()
    if status == "all":
        return "1=1", ()
    if status not in BASKET_STATUSES:
        raise ProjectCenterError("待修改筛选状态不正确")
    return "status=?", (status,)


def _lifecycle_filter(status: str) -> str:
    if status == "active":
        return "status <> 'Abandoned'"
    if status == "all":
        return "1=1"
    if status not in LIFECYCLE_STATUSES:
        raise ProjectCenterError("处理状态不正确")
    return f"status = '{status}'"


def _dedupe_or_none(connection: sqlite3.Connection, operation: str, key: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    clean_key = _idempotency_key(key)
    if not clean_key:
        return None
    existing = repository.idempotency_record(connection, operation, clean_key)
    if not existing:
        return None
    if existing["payload_hash"] != _hash(payload):
        raise ConflictError("这个提交标识已经用于另一条内容，请重新操作")
    return existing


def _save_idempotency(connection: sqlite3.Connection, operation: str, key: Any, entity_type: str, entity_id: str, payload: dict[str, Any], now: str) -> None:
    clean_key = _idempotency_key(key)
    if clean_key:
        repository.save_idempotency(connection, operation=operation, key=clean_key, entity_type=entity_type, entity_id=entity_id, payload_hash=_hash(payload), created_at=now)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _idempotency_key(value: Any) -> str:
    return _clean_text(value or "", "提交标识", maximum=128, required=False)


def _clean_text(value: Any, field: str, *, maximum: int, required: bool = True) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not clean:
        raise ProjectCenterError(f"{field}不能为空")
    if len(clean) > maximum:
        raise ProjectCenterError(f"{field}不能超过 {maximum} 个字")
    return clean


def _clean_module_id(value: Any) -> str:
    clean = _clean_text(value, "模块", maximum=80)
    if not module_by_id(clean):
        raise ProjectCenterError("没有找到这个项目模块")
    return clean


def _clean_optional_module_id(value: Any) -> str:
    clean = _clean_text(value or "", "模块", maximum=80, required=False)
    return _clean_module_id(clean) if clean else ""


def _revision(value: Any) -> int:
    try:
        revision = int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectCenterError("缺少当前版本，请刷新后再试") from exc
    if revision < 1:
        raise ProjectCenterError("当前版本不正确")
    return revision


def _ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ProjectCenterError(f"{field}不能为空")
    result = []
    for item in value:
        clean = _clean_text(item, field, maximum=80)
        if clean not in result:
            result.append(clean)
    if len(result) > 20:
        raise ProjectCenterError(f"一次最多处理 20 条{field}")
    return result


def _lifecycle(value: Any) -> str:
    clean = _clean_text(value, "生命周期状态", maximum=32)
    if clean not in LIFECYCLE_STATUSES:
        raise ProjectCenterError("生命周期状态不正确")
    return clean


def _evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ProjectCenterError("验证结果格式不正确")
    if len(value) > 20:
        raise ProjectCenterError("验证结果不能超过 20 条")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ProjectCenterError("每条验证结果都要是完整说明")
        result.append({
            "observed_at": _clean_text(item.get("observed_at"), "验证时间", maximum=80),
            "environment": _clean_text(item.get("environment"), "验证环境", maximum=120),
            "entry": _clean_text(item.get("entry"), "体验入口", maximum=300),
            "result": _clean_text(item.get("result"), "验证结果", maximum=1200),
            "risk": _clean_text(item.get("risk") or "无", "风险", maximum=600, required=False) or "无",
        })
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _result(status: str, summary: str, data: dict[str, Any], *, gaps: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "summary": summary, "data": data, "gaps": gaps or [], "error": None}
