from __future__ import annotations

import sqlite3
from collections import defaultdict

from xiaoxue_api.research_core import repository


def open_subject(connection: sqlite3.Connection, domain: str, subject_key: str, name: str) -> dict:
    return repository.open_subject(
        connection,
        domain=_required(domain, "领域"),
        subject_key=_required(subject_key, "主体标识"),
        name=_required(name, "主体名称"),
    )


def record_event(
    connection: sqlite3.Connection,
    subject_id: int,
    kind: str,
    title: str,
    occurred_at: str,
    details: str = "",
) -> dict:
    _require_subject(connection, subject_id)
    return repository.add_event(
        connection,
        subject_id=subject_id,
        kind=_required(kind, "事件类型"),
        title=_required(title, "事件标题"),
        occurred_at=_required(occurred_at, "事件时间"),
        details=_clean(details),
    )


def record_material(
    connection: sqlite3.Connection,
    subject_id: int,
    kind: str,
    content: str,
    captured_at: str,
    *,
    source_name: str = "",
    source_url: str = "",
    event_id: int | None = None,
) -> dict:
    _require_subject(connection, subject_id)
    _require_event_for_subject(connection, event_id, subject_id)
    if not _clean(source_name) and not _clean(source_url):
        raise ValueError("原始资料必须保留来源名称或链接")
    return repository.add_material(
        connection,
        subject_id=subject_id,
        event_id=event_id,
        kind=_required(kind, "资料类型"),
        source_name=_clean(source_name),
        source_url=_clean(source_url),
        content=_required(content, "资料内容"),
        captured_at=_required(captured_at, "资料时间"),
    )


def record_user_note(
    connection: sqlite3.Connection,
    subject_id: int,
    content: str,
    *,
    kind: str = "user_note",
    event_id: int | None = None,
) -> dict:
    _require_subject(connection, subject_id)
    _require_event_for_subject(connection, event_id, subject_id)
    return repository.add_note(
        connection,
        subject_id=subject_id,
        event_id=event_id,
        kind=_required(kind, "笔记类型"),
        author="user",
        content=_required(content, "笔记内容"),
    )


def record_digest(connection: sqlite3.Connection, subject_id: int, content: str, *, kind: str = "organized_fact", event_id: int | None = None, source_material_ids: list[int] | None = None) -> dict:
    _require_subject(connection, subject_id)
    _require_event_for_subject(connection, event_id, subject_id)
    material_ids = source_material_ids or []
    if not material_ids:
        raise ValueError("整理结果必须关联至少一条原始资料")
    for material_id in material_ids:
        material = repository.get_material(connection, material_id)
        if not material or material["subject_id"] != subject_id:
            raise LookupError("资料不存在或不属于当前主体")
    return repository.add_digest(connection, subject_id=subject_id, event_id=event_id, kind=_required(kind, "整理类型"), content=_required(content, "整理内容"), source_material_ids=material_ids)


def record_review(connection: sqlite3.Connection, subject_id: int, outcome: str, review: str, *, event_id: int | None = None) -> dict:
    _require_subject(connection, subject_id)
    _require_event_for_subject(connection, event_id, subject_id)
    return repository.add_review(connection, subject_id=subject_id, event_id=event_id, outcome=_required(outcome, "结果"), review=_required(review, "复盘"))


def get_subject_dossier(connection: sqlite3.Connection, subject_id: int) -> dict:
    subject = _require_subject(connection, subject_id)
    events = repository.list_events(connection, subject_id)
    materials = repository.list_materials(connection, subject_id)
    notes = repository.list_notes(connection, subject_id)
    digests = repository.list_digests(connection, subject_id)
    reviews = repository.list_reviews(connection, subject_id)
    groups: dict[str, list[dict]] = defaultdict(list)
    for material in materials:
        groups[material["kind"]].append(material)

    timeline = [
        *({"entry_type": "event", "at": item["occurred_at"], "item": item} for item in events),
        *({"entry_type": "material", "at": item["captured_at"], "item": item} for item in materials),
        *({"entry_type": "note", "at": item["created_at"], "item": item} for item in notes),
        *({"entry_type": "digest", "at": item["created_at"], "item": item} for item in digests),
        *({"entry_type": "review", "at": item["created_at"], "item": item} for item in reviews),
    ]
    timeline.sort(key=lambda entry: (entry["at"], entry["entry_type"]), reverse=True)
    return {
        "subject": subject,
        "events": events,
        "raw_materials": materials,
        "materials_by_kind": dict(groups),
        "user_notes": notes,
        "organized_digests": digests,
        "reviews": reviews,
        "timeline": timeline,
        "boundary": "原始资料、系统整理和用户笔记分层保存；当前核心不生成或覆盖用户判断。",
    }


def list_subjects(connection: sqlite3.Connection, query: str = "", limit: int = 20) -> list[dict]:
    try:
        clean_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("数量必须是整数") from exc
    return repository.list_subjects(connection, query=_clean(query), limit=max(1, min(clean_limit, 100)))


def _require_subject(connection: sqlite3.Connection, subject_id: int) -> dict:
    subject = repository.get_subject(connection, subject_id)
    if not subject:
        raise LookupError("主体不存在")
    return subject


def _require_event_for_subject(connection: sqlite3.Connection, event_id: int | None, subject_id: int) -> None:
    if event_id is None:
        return
    event = repository.get_event(connection, event_id)
    if not event or event["subject_id"] != subject_id:
        raise LookupError("事件不存在或不属于当前主体")


def _required(value: str, label: str) -> str:
    clean = _clean(value)
    if not clean:
        raise ValueError(f"{label}不能为空")
    return clean


def _clean(value: str) -> str:
    return str(value or "").strip()
