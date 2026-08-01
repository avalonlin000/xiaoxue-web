from __future__ import annotations

import re
import sqlite3
from datetime import date

from xiaoxue_api.modules.fundamentals.public import get_match_context
from xiaoxue_api.modules.team_data.public import get_profile_bundle, list_schedules
from xiaoxue_api.modules.tk_knowledge.public import list_match_trading_tk, list_team_trading_notes

from xiaoxue_api.modules.current_event import repository


RUN_MODES = {"virtual_pre", "live", "post_review"}
RUN_PHASES = {"fact_check", "trend", "virtual_judgment", "live_update", "post_review", "complete"}
FACT_STATUSES = {"active", "stale", "excluded", "needs_review", "missing", "user_override"}
TRADE_SECTION_LABELS = {
    "version": "版本与环境",
    "team": "队伍与选手",
    "trend": "已采用规律",
    "matchup": "本场适用性",
    "lineup": "阵容条件",
    "branches": "条件分支",
    "market": "市场对照",
    "plan": "当前交易计划",
    "entry": "入场信号",
    "exit": "退出条件",
    "execution": "实际执行",
    "review": "复盘结论",
}
MATCH_RUN_FOCUS_LABELS = {
    "overview": "单场底稿",
    **TRADE_SECTION_LABELS,
}
TRADE_SECTION_ORDER = tuple(TRADE_SECTION_LABELS)
KNOWLEDGE_TARGETS = {"team", "player", "version", "trading_method"}
KNOWLEDGE_CANDIDATE_STATUSES = {"pending", "ignored", "applied"}


def get_current_event() -> dict:
    config = repository.load_event_config()
    return build_current_event(config, repository.read_plan(config.get("plan_path", "")))


def get_current_event_dashboard(date_value: str = "today", limit: int = 12) -> dict:
    selected_date = _resolve_date(date_value)
    bounded_limit = max(1, min(int(limit or 12), 30))
    matches = list_schedules({"date_from": selected_date, "date_to": selected_date}, bounded_limit)
    return {
        "context": get_current_event(),
        "date": selected_date,
        "matches": [_match_summary(match) for match in matches],
    }


def get_match_desk(
    team_a: str, team_b: str, event: str = "", match_date: str = "today",
    match_time: str = "", match_format: str = "", game: str = "lol",
) -> dict:
    identity = normalize_match_identity({
        "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
        "match_time": match_time, "match_format": match_format, "game": game,
    })
    side_a = identity["team_a"]
    side_b = identity["team_b"]

    quantitative = get_match_context(side_a, side_b, event=event)
    team_a_evidence = _team_evidence(side_a)
    team_b_evidence = _team_evidence(side_b)
    return {
        "match": _identity_payload(identity),
        "quantitative": quantitative,
        "team_a": team_a_evidence,
        "team_b": team_b_evidence,
        "trading_framework": _match_trading_framework(identity, team_a_evidence, team_b_evidence),
        "trading_notes": {
            "team_a": _trading_notes(side_a),
            "team_b": _trading_notes(side_b),
        },
        "boundary": "只汇总当前事实；方向、处理和变化条件由小雪在交易讨论中给出，不自动写交易或长期知识。",
        "workspace": get_match_workspace(identity),
        "match_run": get_match_run(identity),
    }


def get_match_workspace(values: dict) -> dict:
    identity = normalize_match_identity(values)
    row = repository.get_workspace(identity["match_key"])
    if not row:
        return {"exists": False, "match": _identity_payload(identity), "current": None, "changes": []}
    return {
        "exists": True,
        "match": _identity_payload(identity),
        "current": _workspace_current(row),
        "changes": [_observation_payload(item) for item in repository.list_observations(row["id"])],
    }


def save_match_workspace(values: dict) -> dict:
    identity = normalize_match_identity(values)
    current = _normalize_current_judgment(values)
    row = repository.upsert_workspace({**identity, **current})
    return {
        "ok": True,
        "match": _identity_payload(identity),
        "current": _workspace_current(row),
        "changes": [_observation_payload(item) for item in repository.list_observations(row["id"])],
    }


def record_match_change(values: dict) -> dict:
    identity = normalize_match_identity(values)
    source = _limited_text(values.get("source"), "变化来源", 40)
    impact = _limited_text(values.get("impact"), "影响", 20)
    detail = _limited_text(values.get("detail"), "变化内容", 500)
    if not detail:
        raise ValueError("变化内容不能为空")
    if source not in {"与小雪讨论", "首发", "BP", "盘口", "比赛", "其他"}:
        raise ValueError("变化来源不支持")
    if impact not in {"维持", "加强", "削弱", "推翻", "观察"}:
        raise ValueError("影响只支持维持、加强、削弱、推翻或观察")
    workspace = repository.get_workspace(identity["match_key"])
    if not workspace:
        raise LookupError("先保存这场的当前判断，再记录变化")
    row = repository.create_observation(workspace["id"], {"source": source, "impact": impact, "detail": detail})
    return {"ok": True, "match": _identity_payload(identity), "change": _observation_payload(row)}


def start_match_run(values: dict) -> dict:
    """Open or resume one temporary match trade thread.

    The thread is only a working context. Long-term knowledge continues to live on
    teams, players, version understanding and the user's trading method.
    """
    identity = _resolve_run_identity(values)
    mode = _normalize_run_mode(values.get("mode") or "live")
    requested_focus = _normalize_match_run_focus(values.get("focus"))
    existing = repository.get_match_run_by_identity(identity)
    if not existing:
        cutoff_at = _cutoff_at(identity)
        row = repository.create_match_run({
            **identity, "match_key": _match_run_key(identity), "mode": mode, "cutoff_at": cutoff_at,
            "focus": requested_focus or "overview",
        })
        repository.create_match_run_facts(row["id"], _collect_run_facts(identity, cutoff_at, mode))
    else:
        row = existing
    row = repository.activate_match_run(row["id"], focus=requested_focus, mode=mode)
    return _match_run_payload(row)


def get_match_run(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = repository.get_match_run_by_identity(identity)
    if not row:
        return {
            "exists": False,
            "match": _identity_payload(identity),
            "guide": {
                "focus": "overview",
                "focus_label": "单场底稿",
                "can_jump": True,
                "modules": [
                    {"id": item, "label": label}
                    for item, label in TRADE_SECTION_LABELS.items()
                ],
            },
        }
    return _match_run_payload(row)


def get_active_match_run() -> dict:
    row = repository.get_active_match_run()
    if not row:
        return {
            "exists": False,
            "guide": {
                "focus": "overview",
                "focus_label": "单场底稿",
                "can_jump": True,
                "modules": [
                    {"id": item, "label": label}
                    for item, label in TRADE_SECTION_LABELS.items()
                ],
            },
        }
    return _match_run_payload(row)


def list_recent_match_runs(limit: int = 12) -> dict:
    bounded = max(1, min(int(limit or 12), 30))
    return {"matches": [_match_run_summary(row) for row in repository.list_recent_match_runs(bounded)]}


def pause_match_run(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    return _match_run_payload(repository.pause_match_run(row["id"]))


def focus_match_run(values: dict) -> dict:
    """Move the temporary thread to a module without creating a judgment."""
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    focus = _normalize_match_run_focus(values.get("focus"), required=True)
    return _match_run_payload(repository.activate_match_run(row["id"], focus=focus))


def save_match_trade_entry(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    section = _limited_text(values.get("section"), "交易环节", 30).lower()
    if section not in TRADE_SECTION_LABELS:
        raise ValueError("交易环节不支持")
    content = _limited_text(values.get("content"), TRADE_SECTION_LABELS[section], 1200)
    if not content:
        raise ValueError(f"{TRADE_SECTION_LABELS[section]}不能为空")
    if section == "trend" and values.get("confirmed_by_user") is not True:
        raise ValueError("采用通用交易 TK 必须经过用户确认")
    repository.activate_match_run(row["id"], focus=section)
    repository.upsert_match_run_entry(row["id"], section, content)
    return _match_run_payload(repository.get_match_run_by_identity(identity))


def create_knowledge_candidate(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    target_type = _limited_text(values.get("target_type"), "长期更新对象", 30).lower()
    if target_type not in KNOWLEDGE_TARGETS:
        raise ValueError("长期更新对象只支持队伍、选手、版本或交易方法")
    target_name = _limited_text(values.get("target_name"), "对象名称", 80)
    if target_type == "team" and target_name.upper() not in {identity["team_a"], identity["team_b"]}:
        raise ValueError("队伍候选必须属于当前比赛双方")
    if not target_name:
        target_name = "当前版本" if target_type == "version" else "个人交易方法"
    candidate = repository.create_knowledge_candidate(row["id"], {
        "target_type": target_type,
        "target_name": target_name,
        "topic": _required_limited_text(values.get("topic"), "更新主题", 120),
        "observation": _required_limited_text(values.get("observation"), "新观察", 1000),
        "reason": _required_limited_text(values.get("reason"), "为什么值得整理", 500),
    })
    return {"ok": True, "candidate": _knowledge_candidate_payload(candidate, identity)}


def list_knowledge_candidates(status: str = "pending", limit: int = 100) -> dict:
    clean_status = _limited_text(status or "pending", "候选状态", 20).lower()
    if clean_status not in KNOWLEDGE_CANDIDATE_STATUSES:
        raise ValueError("候选状态不支持")
    bounded = max(1, min(int(limit or 100), 200))
    rows = repository.list_knowledge_candidates(clean_status, bounded)
    return {"status": clean_status, "candidates": [_knowledge_candidate_payload(row) for row in rows]}


def update_knowledge_candidate_status(candidate_id: int, status: str) -> dict:
    clean_status = _limited_text(status, "候选状态", 20).lower()
    if clean_status not in KNOWLEDGE_CANDIDATE_STATUSES:
        raise ValueError("候选状态不支持")
    row = repository.update_knowledge_candidate_status(int(candidate_id), clean_status)
    if not row:
        raise LookupError("阶段整理候选不存在")
    return {"ok": True, "candidate": _knowledge_candidate_payload(row)}


def update_match_run_fact(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    try:
        fact_id = int(values.get("fact_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("要修改哪条依据不明确") from exc
    status = _limited_text(values.get("status"), "依据状态", 30).lower()
    if status not in FACT_STATUSES:
        raise ValueError("依据状态只支持采用、待更新、排除、待确认、缺失或用户覆盖")
    value = _limited_text(values.get("value"), "依据内容", 800)
    reason = _limited_text(values.get("reason"), "修改原因", 300)
    if not value or not reason:
        raise ValueError("修改依据时必须说明新内容和原因")
    changed = repository.update_match_run_fact(row["id"], fact_id, status=status, value=value, reason=reason)
    if not changed:
        raise LookupError("这条依据不属于当前比赛")
    return {"ok": True, "match": _identity_payload(identity), "fact": _run_fact_payload(changed), "guide": _run_guide(row)}


def advance_match_run(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    phase = _limited_text(values.get("phase"), "流程阶段", 40).lower()
    if phase not in RUN_PHASES:
        raise ValueError("流程阶段不支持")
    if row["mode"] == "virtual_pre" and phase in {"post_review", "complete"} and not row["result_unlocked"]:
        raise ValueError("赛前模拟尚未解封赛果；明确说“解封赛果”后才能进入复盘")
    updated = repository.update_match_run_state(row["id"], phase=phase)
    return _match_run_payload(updated)


def save_virtual_judgment(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    if row["mode"] == "post_review":
        raise ValueError("复盘模式不再保存赛前虚拟判断")
    judgment = _normalize_current_judgment(values)
    updated = repository.update_match_run_state(row["id"], phase="virtual_judgment", judgment=judgment)
    return _match_run_payload(updated)


def unlock_match_run_result(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    if row["mode"] != "virtual_pre":
        raise ValueError("赛果封存只用于历史比赛调试；正常比赛复盘直接读取真实赛果")
    updated = repository.update_match_run_state(row["id"], phase="post_review", result_unlocked=True)
    return _match_run_payload(updated)


def get_score_match_evidence(values: dict) -> dict:
    """Return only ScoreGG-imported facts, and never leak a sealed result."""
    identity = _resolve_run_identity(values)
    view = _limited_text(values.get("view") or "pre", "查看阶段", 20).lower()
    if view not in {"pre", "post"}:
        raise ValueError("查看阶段只支持 pre 或 post")
    row = _require_match_run(identity)
    if view == "post" and row["mode"] == "virtual_pre" and not row["result_unlocked"]:
        raise ValueError("赛果仍封存；明确说“解封赛果”后才能查看赛后资料")

    schedule = repository.get_score_schedule(identity)
    score_match = {
        "schedule": _score_schedule_payload(schedule),
        "team_a_form": _score_form_payload(repository.list_score_team_form(identity["team_a"], row["cutoff_at"]), identity["team_a"]),
        "team_b_form": _score_form_payload(repository.list_score_team_form(identity["team_b"], row["cutoff_at"]), identity["team_b"]),
    }
    if view == "post":
        score_match["result"] = _score_result_payload(repository.get_score_result(identity))
    return {
        "match": _identity_payload(identity),
        "view": view,
        "source": "ScoreGG 导入库（只读）",
        "score_match": score_match,
    }


def get_match_run_review(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    if row["mode"] == "virtual_pre" and not row["result_unlocked"]:
        raise ValueError("先明确说“解封赛果”，再开始赛后复盘")
    payload = _match_run_payload(row)
    payload["score_evidence"] = get_score_match_evidence({**identity, "view": "post"})
    return payload


def _normalize_run_mode(value) -> str:
    mode = _limited_text(value, "运行模式", 30).lower()
    if mode not in RUN_MODES:
        raise ValueError("运行模式只支持 virtual_pre、live 或 post_review")
    return mode


def _normalize_match_run_focus(value, *, required: bool = False) -> str | None:
    focus = _limited_text(value, "当前模块", 30).lower()
    if not focus:
        if required:
            raise ValueError("当前模块不能为空")
        return None
    if focus not in MATCH_RUN_FOCUS_LABELS:
        raise ValueError("当前模块不支持")
    return focus


def _resolve_run_identity(values: dict) -> dict:
    """Complete a chat-provided matchup from its ScoreGG schedule before storing it."""
    identity = normalize_match_identity(values)
    if identity["match_time"] and identity["match_format"] and identity["event"]:
        return identity
    schedule = repository.get_score_schedule(identity)
    if not schedule:
        return identity
    event = identity["event"] or " ".join(filter(None, (schedule["region"], schedule["stage"])))
    completed = {
        **identity,
        "event": event,
        "match_time": identity["match_time"] or schedule["time_bjt"],
        "match_format": identity["match_format"] or schedule["format"],
    }
    return normalize_match_identity(completed)


def _cutoff_at(identity: dict) -> str:
    time_value = identity["match_time"] or "00:00"
    return f"{identity['match_date']} {time_value}:00"


def _require_match_run(identity: dict):
    row = repository.get_match_run_by_identity(identity)
    if not row:
        raise LookupError("这场还没有打开交易推演")
    return row


def _match_run_key(identity: dict) -> str:
    """Event wording changes; the scheduled sides and kickoff identify a run."""
    return "|".join((
        identity["game"], identity["team_a"].casefold(), identity["team_b"].casefold(),
        identity["match_date"], identity["match_time"].casefold(),
    ))


def _collect_run_facts(identity: dict, cutoff_at: str, mode: str) -> list[dict]:
    """Make a small, inspectable ledger instead of one opaque diagnosis paragraph."""
    facts: list[dict] = []
    schedule = repository.get_score_schedule(identity)
    if schedule:
        facts.append({
            "fact_code": "E01", "kind": "quantitative", "label": "ScoreGG 赛程",
            "value": _schedule_text(schedule), "source": "scoregg_schedule", "source_ref": schedule["source"] or "",
            "as_of": schedule["updated_at"] or "", "status": "active", "affects": "比赛身份",
            "action": "比赛身份已核对，可继续。",
        })
    else:
        facts.append({
            "fact_code": "E01", "kind": "quantitative", "label": "ScoreGG 赛程",
            "value": "导入库未找到这场赛程", "source": "scoregg_schedule", "source_ref": "", "as_of": "",
            "status": "missing", "affects": "比赛身份", "action": "补比赛日期、时间或队名后重试。",
        })

    for index, team in enumerate((identity["team_a"], identity["team_b"]), start=1):
        base = 10 + (index - 1) * 10
        evidence = _team_evidence(team)
        starters = evidence.get("starters") or []
        starter_value = "、".join(f"{item['role']} {item['name']}" for item in starters) or "未录入首发"
        facts.append({
            "fact_code": f"E{base + 1:02d}", "kind": "qualitative", "label": f"{team} 首发",
            "value": starter_value, "source": "team_profile", "source_ref": team, "as_of": "",
            "status": "active" if starters else "missing",
            "affects": "阵容与对线", "action": "这是已录入的队伍首发资料；是否作为当场首发由你决定。",
        })

        three_d = evidence.get("three_dimensional") or {}
        d3_value = "；".join(
            f"{item['label']}：{item['value']}" for item in (three_d.get("items") or []) if item.get("value")
        ) or three_d.get("version_understanding") or "未录入三维资料"
        d3_status, d3_action = "active", _source_time_action(three_d.get("updated_at") or "")
        if not d3_value or d3_value == "未录入三维资料":
            d3_status, d3_action = "missing", "补一条本场相关的风格或版本观察。"
        facts.append({
            "fact_code": f"E{base + 2:02d}", "kind": "qualitative", "label": f"{team} 三维 / 版本理解",
            "value": d3_value, "source": "team_3d", "source_ref": team,
            "as_of": three_d.get("updated_at") or "", "status": d3_status, "affects": "风格与版本适配",
            "action": d3_action,
        })

        notes = _trading_notes(team)
        note_value = "；".join(item["hint"] for item in notes if item.get("hint")) or "没有可用的队伍交易备注"
        facts.append({
            "fact_code": f"E{base + 3:02d}", "kind": "qualitative", "label": f"{team} 交易备注",
            "value": note_value, "source": "trading_note", "source_ref": team, "as_of": "",
            "status": "active" if notes else "missing", "affects": "条件判断",
            "action": "这是已有交易备注；是否用于这场由你决定。" if notes else "这场没有可直接套用的交易备注。",
        })

        form = repository.list_score_team_form(team, cutoff_at)
        facts.append({
            "fact_code": f"E{base + 4:02d}", "kind": "quantitative", "label": f"{team} 赛前近况",
            "value": _score_form_text(form, team), "source": "scoregg_form", "source_ref": team,
            "as_of": cutoff_at, "status": "active" if form else "missing", "affects": "近期强弱",
            "action": "ScoreGG 赛前历史已加载。" if form else "ScoreGG 导入库没有足够的赛前记录。",
        })

    try:
        quantitative = get_match_context(identity["team_a"], identity["team_b"], event=identity["event"])
        ts_value = _ts_text(quantitative)
    except LookupError:
        ts_value = "TS 底表未找到完整对照"
    facts.append({
        "fact_code": "E31", "kind": "quantitative", "label": "当前 TS 对照",
        "value": ts_value, "source": "team_ts", "source_ref": f"{identity['team_a']},{identity['team_b']}", "as_of": "",
        "status": "active", "affects": "强弱判断",
        "action": "这是当前 TS，不等于赛前 TS；是否用于这场由你决定。" if mode == "virtual_pre" else "当前 TS 已列出；是否采用由你决定。",
    })
    return facts


def _source_time_action(as_of: str) -> str:
    if as_of:
        return f"资料记录于 {as_of}；是否仍适用于本场由你决定。"
    return "资料没有记录时间；是否仍适用于本场由你决定。"


def _match_run_payload(row) -> dict:
    facts = [_run_fact_payload(item) for item in repository.list_match_run_facts(row["id"])]
    identity = _identity_payload(row)
    virtual = None
    if row["virtual_direction"]:
        virtual = {
            "direction": row["virtual_direction"], "reasons": row["virtual_reasons"],
            "handling": row["virtual_handling"], "change_conditions": row["virtual_change_conditions"],
        }
    return {
        "exists": True,
        "id": row["id"], "match": identity, "mode": row["mode"], "phase": row["phase"],
        "cutoff_at": row["cutoff_at"], "result_unlocked": bool(row["result_unlocked"]),
        "activity_status": row["activity_status"], "focus": row["current_focus"],
        "entries": [_run_entry_payload(item) for item in repository.list_match_run_entries(row["id"])],
        "facts": facts, "virtual_judgment": virtual,
        "trading_framework": _match_trading_framework(identity),
        "revisions": [_run_revision_payload(item) for item in repository.list_match_run_revisions(row["id"])],
        "guide": _run_guide(row, facts), "updated_at": row["updated_at"],
        "debug_replay": {
            "enabled": row["mode"] == "virtual_pre",
            "result_available": bool(row["result_unlocked"]),
        },
    }


def _run_fact_payload(row) -> dict:
    status = "needs_review" if row["status"] == "stale" else row["status"]
    return {
        "id": row["id"], "kind": row["kind"], "label": row["label"],
        "value": row["value"], "source": row["source"], "source_ref": row["source_ref"], "as_of": row["as_of"],
        "status": status, "affects": row["affects"], "action": row["action"], "updated_at": row["updated_at"],
    }


def _run_entry_payload(row) -> dict:
    return {
        "section": row["section"], "label": TRADE_SECTION_LABELS.get(row["section"], row["section"]),
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
        "modules": [
            {"id": item, "label": label}
            for item, label in TRADE_SECTION_LABELS.items()
        ],
    }


def _match_run_summary(row) -> dict:
    return {
        "id": row["id"], "match": _identity_payload(row), "activity_status": row["activity_status"],
        "focus": row["current_focus"], "focus_label": MATCH_RUN_FOCUS_LABELS.get(row["current_focus"], "单场底稿"),
        "updated_at": row["updated_at"], "last_opened_at": row["last_opened_at"],
    }


def _knowledge_candidate_payload(row, identity: dict | None = None) -> dict:
    match = identity or row
    return {
        "id": row["id"], "target_type": row["target_type"], "target_name": row["target_name"],
        "topic": row["topic"], "observation": row["observation"], "reason": row["reason"],
        "status": row["status"], "match": _identity_payload(match),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _score_schedule_payload(row) -> dict | None:
    if not row:
        return None
    return {
        "date": row["date"], "time": row["time_bjt"], "team_a": row["team_a"], "team_b": row["team_b"],
        "region": row["region"], "format": row["format"], "stage": row["stage"],
        "source_ref": row["source"], "updated_at": row["updated_at"],
    }


def _score_result_payload(row) -> dict | None:
    if not row:
        return None
    return {
        "match_id": row["match_id"], "status": row["status"], "winner": row["winner"],
        "score_a": row["score_a"], "score_b": row["score_b"], "match_time": row["match_time"],
        "format": row["game_format"], "stage": row["stage"], "updated_at": row["updated_at"],
    }


def _score_form_payload(rows, team: str) -> list[dict]:
    return [{
        "match_id": row["match_id"], "opponent": row["team_b_id"] if row["team_a_id"] == team else row["team_a_id"],
        "winner": row["winner"], "score": _relative_score(row, team), "match_time": row["match_time"],
        "stage": row["stage"],
    } for row in rows]


def _schedule_text(row) -> str:
    return f"{row['date']} {row['time_bjt']} · {row['region'] or ''} {row['stage'] or ''} · {row['format'] or ''}".strip()


def _score_form_text(rows, team: str) -> str:
    if not rows:
        return "ScoreGG 导入库没有赛前历史记录"
    values = []
    for row in rows[:5]:
        opponent = row["team_b_id"] if row["team_a_id"] == team else row["team_a_id"]
        mark = "胜" if row["winner"] == team else "负"
        values.append(f"{mark}{opponent} {_relative_score(row, team)}")
    return "；".join(values)


def _relative_score(row, team: str) -> str:
    if row["team_a_id"] == team:
        return f"{row['score_a']}:{row['score_b']}"
    return f"{row['score_b']}:{row['score_a']}"


def _ts_text(quantitative: dict) -> str:
    left = quantitative.get("team_a") or {}
    right = quantitative.get("team_b") or {}
    return f"{left.get('team', 'A')} TS {left.get('ts', '—')} / {right.get('team', 'B')} TS {right.get('ts', '—')}"


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


def _resolve_date(value: str) -> str:
    raw = str(value or "today").strip().lower()
    if raw == "today":
        return date.today().isoformat()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("date 只支持 today 或 YYYY-MM-DD") from exc


def normalize_match_identity(values: dict) -> dict:
    team_a = _clean_team(values.get("team_a"), "队伍A").upper()
    team_b = _clean_team(values.get("team_b"), "队伍B").upper()
    if team_a == team_b:
        raise ValueError("两边队伍不能相同")
    game = _limited_text(values.get("game") or "lol", "项目", 20).lower()
    if game != "lol":
        raise ValueError("当前只支持 LOL 比赛工作台")
    event = _limited_text(values.get("event"), "赛事", 120)
    match_date = _resolve_date(values.get("match_date") or "today")
    match_time = _normalize_match_time(values.get("match_time"))
    match_format = _limited_text(values.get("match_format"), "赛制", 40)
    normalized_event = " ".join(event.casefold().split())
    match_key = "|".join((game, team_a.casefold(), team_b.casefold(), normalized_event, match_date, match_time.casefold()))
    return {
        "match_key": match_key, "game": game, "team_a": team_a, "team_b": team_b, "event": event,
        "match_date": match_date, "match_time": match_time, "match_format": match_format,
    }


def _normalize_current_judgment(values: dict) -> dict:
    current = {
        "direction": _limited_text(values.get("direction"), "方向", 160),
        "reasons": _limited_text(values.get("reasons"), "理由", 700),
        "handling": _limited_text(values.get("handling"), "处理", 500),
        "change_conditions": _limited_text(values.get("change_conditions"), "变化条件", 500),
    }
    if not all(current.values()):
        raise ValueError("当前判断必须包含方向、理由、处理和变化条件")
    return current


def _limited_text(value, label: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValueError(f"{label}不能超过 {limit} 个字")
    return text


def _required_limited_text(value, label: str, limit: int) -> str:
    text = _limited_text(value, label, limit)
    if not text:
        raise ValueError(f"{label}不能为空")
    return text


def _normalize_match_time(value) -> str:
    raw = _limited_text(value, "比赛时间", 40)
    if not raw:
        return ""
    candidate = raw.replace("T", " ").split()[-1]
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", candidate)
    if not match:
        return raw
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _identity_payload(identity: dict) -> dict:
    return {
        key: identity[key]
        for key in ("game", "team_a", "team_b", "event", "match_date", "match_time", "match_format")
    }


def _workspace_current(row) -> dict:
    return {
        "direction": row["current_direction"],
        "reasons": row["current_reasons"],
        "handling": row["current_handling"],
        "change_conditions": row["change_conditions"],
        "updated_at": row["updated_at"],
    }


def _observation_payload(row) -> dict:
    return {
        "id": row["id"], "source": row["source"], "impact": row["impact"],
        "detail": row["detail"], "created_at": row["created_at"],
    }


def _clean_team(value: str, label: str) -> str:
    team = str(value or "").strip()
    if not team:
        raise ValueError(f"{label}不能为空")
    if len(team) > 40:
        raise ValueError(f"{label}过长")
    return team


def _match_summary(match: dict) -> dict:
    team_a = str(match.get("team_a") or "").strip()
    team_b = str(match.get("team_b") or "").strip()
    try:
        quantitative = get_match_context(team_a, team_b, event=match.get("stage") or match.get("region") or "")
        ts = {"available": True, **quantitative}
    except LookupError as exc:
        ts = {"available": False, "reason": str(exc)}
    return {"match": match, "ts": ts}


def _team_evidence(team: str) -> dict:
    bundle = get_profile_bundle(team) or {}
    three_dimensional = bundle.get("three_dimensional") or {}
    return {
        "team": team,
        "starters": bundle.get("players") or [],
        "three_dimensional": {
            "items": [
                {"label": three_dimensional.get(name) or "", "value": three_dimensional.get(value) or ""}
                for name, value in (
                    ("dim_1_name", "dim_1_value"),
                    ("dim_2_name", "dim_2_value"),
                    ("dim_3_name", "dim_3_value"),
                )
                if three_dimensional.get(name) or three_dimensional.get(value)
            ],
            "version_understanding": three_dimensional.get("version_understanding") or "",
            "updated_at": three_dimensional.get("updated_at") or "",
        },
    }


def _trading_notes(team: str) -> list[dict]:
    try:
        notes = list_team_trading_notes(team, status="active", limit=3).get("notes") or []
    except (LookupError, OSError, RuntimeError, ValueError):
        return []
    return [{
        "title": note.get("title") or f"{team} 交易 TK",
        "hint": note.get("daily_hint") or note.get("original") or "",
        "market": note.get("market_label") or note.get("market") or "",
        "scenario": note.get("scenario") or "",
    } for note in notes]


def _event_region(event: str) -> str:
    text = (event or "").upper()
    for region in ("LPL", "LCK", "LCP", "LEC", "LTA", "LCS"):
        if region in text:
            return region
    return ""


def _match_trading_framework(identity: dict, team_a_evidence: dict | None = None, team_b_evidence: dict | None = None) -> dict:
    """Return only the already-recorded TK that can matter to this matchup.

    The list is deliberately separate from the stored match facts: editing a TK
    later should be visible when a paused match is reopened, without turning a
    reminder into an adopted trend inside the match thread.
    """
    side_a = identity["team_a"]
    side_b = identity["team_b"]
    try:
        evidence_a = team_a_evidence if team_a_evidence is not None else _team_evidence(side_a)
        evidence_b = team_b_evidence if team_b_evidence is not None else _team_evidence(side_b)
    except (LookupError, OSError, RuntimeError, ValueError, sqlite3.Error):
        evidence_a, evidence_b = {}, {}
    players = [
        player.get("name") or player.get("player_name") or ""
        for player in [*(evidence_a.get("starters") or []), *(evidence_b.get("starters") or [])]
    ]
    return list_match_trading_tk(_event_region(identity.get("event") or ""), [side_a, side_b], players, limit=8)


def _title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return "当前交易预案"
