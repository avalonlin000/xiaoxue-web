from __future__ import annotations

from typing import Any

from xiaoxue_api.core.module_registry import capability_result

from . import repository




def get_global_version_understanding() -> dict[str, Any]:
    item = repository.get_unified_version_understanding()
    if not item:
        return capability_result(
            "empty",
            summary="当前版本正文暂时读不到",
            data={"item": None, "current_mainline": None},
            sources=[],
            effects={"read_only": True, "database_writes": 0},
            gaps=["统一版本理解对象（id=229）不存在或暂时不可读"],
        )

    return capability_result(
        "ok",
        summary="已读取统一版本理解对象",
        data={"item": item, "current_mainline": _current_mainline(item)},
        sources=[{
            "source": "shared_version_analysis",
            "id": item["id"],
            "created_at": item["created_at"],
            "content_type": item["content_type"],
        }],
        effects={"read_only": True, "database_writes": 0},
    )


def _current_mainline(item: dict[str, Any]) -> dict[str, Any]:
    content = str(item.get("content") or "").strip()
    return {
        "title": str(item.get("topic") or "当前版本理解"),
        "content": content,
        "source_object_id": item["id"],
    }
