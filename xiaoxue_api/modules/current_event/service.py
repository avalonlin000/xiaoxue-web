from __future__ import annotations

from xiaoxue_api.modules.current_event import repository


def get_current_event() -> dict:
    config = repository.load_event_config()
    return build_current_event(config, repository.read_plan(config.get("plan_path", "")))


def build_current_event(config: dict, plan: dict | None) -> dict:
    content = str((plan or {}).get("content") or "").strip()
    title = _title(content) if content else ""
    return {
        "event": config.get("event", "当前赛事"),
        "phase": config.get("phase", ""),
        "knowledge_query": config.get("knowledge_query", config.get("event", "")),
        "plan_status": "ready" if content else "not_created",
        "plan_title": title,
        "plan_content": content,
        "plan_updated_at": (plan or {}).get("updated_at", ""),
        "plan_boundary": "完整预案只在与小雪确认后写入；工作台不自动生成。",
    }


def _title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return "当前交易预案"
