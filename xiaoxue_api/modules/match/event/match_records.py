"""Single-match record vocabulary and read projections; no storage or model calls.

The service owns identity resolution, permissions and persistence. These helpers
only present existing records, so rendering never saves or revises a judgment.
"""
from __future__ import annotations


RUN_MODES = {"virtual_pre", "live", "post_review"}
RUN_PHASES = {"fact_check", "trend", "virtual_judgment", "live_update", "post_review", "complete"}
FACT_STATUSES = {"active", "stale", "excluded", "needs_review", "missing", "user_override"}
FACT_STATUS_LABELS = {
    "active": "采用", "stale": "待更新", "excluded": "排除",
    "needs_review": "待确认", "missing": "缺失", "user_override": "用户覆盖",
}
MATCH_RUN_ENTRY_META = {
    "version": {"label": "版本与环境", "stage": "pre", "purpose": "确认本场适用的版本和比赛环境。"},
    "team": {"label": "队伍与选手", "stage": "pre", "purpose": "确认双方队伍、选手和当前打法背景。"},
    "trend": {"label": "已采用规律", "stage": "pre", "purpose": "记录已经确认要放进本场的规律。"},
    "matchup": {"label": "本场适用性", "stage": "pre", "purpose": "判断已有认识在这场如何延续或被破坏。"},
    "lineup": {"label": "阵容条件", "stage": "live", "purpose": "记录 BP 和首发是否支持原判断。"},
    "branches": {"label": "条件分支", "stage": "pre", "purpose": "写清不同剧本出现时怎么处理。"},
    "market": {"label": "市场对照", "stage": "pre", "purpose": "对照市场共识、分歧和仍未知的部分。"},
    "plan": {"label": "当前交易计划", "stage": "pre", "purpose": "保留原计划和不碰条件。"},
    "entry": {"label": "入场信号", "stage": "pre", "purpose": "记录什么现象出现后才考虑执行。"},
    "exit": {"label": "退出条件", "stage": "pre", "purpose": "记录判断失效或需要退出的条件。"},
    "execution": {"label": "实际执行", "stage": "live", "purpose": "记录比赛中实际做了什么。"},
    "review": {"label": "复盘结论", "stage": "post", "purpose": "对照实际发生、判断和执行，留下下次校准。"},
}
TRADE_SECTION_LABELS = {section: meta["label"] for section, meta in MATCH_RUN_ENTRY_META.items()}
MATCH_RUN_FOCUS_LABELS = {"overview": "单场底稿", **TRADE_SECTION_LABELS}
TRADE_SECTION_ORDER = tuple(TRADE_SECTION_LABELS)
MATCH_RUN_STAGE_META = {
    "pre": {"label": "赛前", "purpose": "判断基础、主要矛盾、计划和不碰条件。"},
    "live": {"label": "赛中", "purpose": "对照 BP、首发、比赛和市场变化，记录实际执行。"},
    "post": {"label": "赛后", "purpose": "回看实际发生、判断与执行，并留下可复用候选。"},
}
KNOWLEDGE_TARGETS = {"team", "player", "version", "trading_method"}
KNOWLEDGE_CANDIDATE_STATUSES = {"pending", "ignored", "applied"}


def _run_fact_payload(row) -> dict:
    status = "needs_review" if row["status"] == "stale" else row["status"]
    return {
        "id": row["id"], "kind": row["kind"], "label": row["label"],
        "value": row["value"], "source": row["source"], "source_ref": row["source_ref"], "as_of": row["as_of"],
        "status": status, "affects": row["affects"], "action": row["action"], "updated_at": row["updated_at"],
    }


def _run_entry_payload(row) -> dict:
    metadata = MATCH_RUN_ENTRY_META.get(row["section"], {})
    return {
        "section": row["section"], "label": TRADE_SECTION_LABELS.get(row["section"], row["section"]),
        "stage": metadata.get("stage", "pre"), "purpose": metadata.get("purpose", ""),
        "content": row["content"], "updated_at": row["updated_at"],
    }


def _run_revision_payload(row) -> dict:
    return {
        "id": row["id"], "fact_id": row["fact_id"], "old_status": row["old_status"],
        "new_status": row["new_status"], "old_value": row["old_value"], "new_value": row["new_value"],
        "reason": row["reason"], "created_at": row["created_at"],
    }


def _run_guide(row, facts: list[dict] | None = None) -> dict:
    focus = row["current_focus"] if row["current_focus"] in MATCH_RUN_FOCUS_LABELS else "overview"
    return {
        "focus": focus,
        "focus_label": MATCH_RUN_FOCUS_LABELS[focus],
        "can_jump": True,
        "stages": _run_stage_groups(),
        "modules": [
            {"id": item, "label": meta["label"], "stage": meta["stage"], "purpose": meta["purpose"]}
            for item, meta in MATCH_RUN_ENTRY_META.items()
        ],
    }


def _empty_run_guide() -> dict:
    return _run_guide({"current_focus": "overview"})


def _run_stage_groups() -> dict:
    return {
        stage: {
            "id": stage,
            "label": stage_meta["label"],
            "purpose": stage_meta["purpose"],
            "modules": [
                {"id": section, "label": entry_meta["label"], "stage": stage, "purpose": entry_meta["purpose"]}
                for section, entry_meta in MATCH_RUN_ENTRY_META.items()
                if entry_meta["stage"] == stage
            ],
        }
        for stage, stage_meta in MATCH_RUN_STAGE_META.items()
    }
