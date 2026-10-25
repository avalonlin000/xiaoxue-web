from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from xiaoxue_api.modules.team.public import get_match_context
from xiaoxue_api.modules.team.public import get_profile_bundle, list_schedules
from xiaoxue_api.modules.knowledge.tk.public import list_match_trading_tk, list_team_trading_notes
from xiaoxue_api.modules.knowledge.version.public import get_global_version_understanding
from xiaoxue_api.modules.gol_gg.public import series_facts as gol_series_facts

from xiaoxue_api.modules.current_event import repository
from . import preparation
from .trade_plan import (
    PLAN_MARKETS, _json_object, _auto_trade_plan_from_storage, _empty_manual_trade_plan,
    _manual_trade_plan, _frozen_trade_plan, _compose_trade_plan, _ordered_ids,
)
from .match_records import (
    RUN_MODES, RUN_PHASES, FACT_STATUSES, FACT_STATUS_LABELS, MATCH_RUN_ENTRY_META,
    TRADE_SECTION_LABELS, MATCH_RUN_FOCUS_LABELS, TRADE_SECTION_ORDER,
    MATCH_RUN_STAGE_META, KNOWLEDGE_TARGETS, KNOWLEDGE_CANDIDATE_STATUSES,
    _run_fact_payload, _run_entry_payload, _run_revision_payload,
    _run_guide, _empty_run_guide, _run_stage_groups,
)
TRADING_METHODS_PATH = Path(__file__).resolve().parents[3] / "config" / "trading-methods.json"


def get_current_event() -> dict:
    config = repository.load_event_config()
    return build_current_event(config, repository.read_plan(config.get("plan_path", "")))


def get_current_event_scope_leagues() -> list[str]:
    """当前赛事在赛程里的范围（schedules.stage 匹配列表）；未配置时不过滤。"""
    try:
        config = repository.load_event_config()
    except (OSError, ValueError, TypeError):
        return []
    return [str(item).strip() for item in (config.get("leagues") or []) if str(item).strip()]


def match_in_current_event_scope(match: dict, leagues: list[str] | None = None) -> bool:
    """判断一条赛程是否属于当前赛事范围；空范围视为全部属于。"""
    scope = get_current_event_scope_leagues() if leagues is None else leagues
    if not scope:
        return True
    stage = str(match.get("stage") or "")
    return any(league.casefold() in stage.casefold() for league in scope)


def get_trading_methods() -> dict:
    from .judgment import catalogue
    return catalogue(TRADING_METHODS_PATH)


def get_judgment_context(**values) -> dict:
    from .judgment import context
    return context(values, get_trading_methods())


def discuss_judgment(**values) -> dict:
    from .judgment import discuss
    return discuss(values, get_trading_methods())


def get_current_event_dashboard(date_value: str = "today", limit: int = 12, *, now_value: datetime | None = None) -> dict:
    config = get_current_event()
    upcoming = date_value == "upcoming"
    window_start = now_value or datetime.now(preparation.ZONE)
    if window_start.tzinfo is None:
        raise ValueError("近期比赛窗口必须包含时区")
    window_start = window_start.astimezone(preparation.ZONE)
    selected_date = window_start.date().isoformat() if upcoming else _resolve_date(date_value)
    date_to = (date.fromisoformat(selected_date) + timedelta(days=preparation.window_days(config))).isoformat() if upcoming else selected_date
    window_end = window_start + timedelta(days=preparation.window_days(config)) if upcoming else None
    bounded_limit = max(1, min(int(limit or 12), 200))
    leagues = get_current_event_scope_leagues()
    rows, overflow = preparation.schedules(list_schedules, {**config, "leagues": leagues}, selected_date, date_to)
    matches = [
        match
        for match in rows
        if match_in_current_event_scope(match, leagues)
        and (not upcoming or _match_in_preparation_window(match, window_start, window_end))
    ]
    return {
        "context": config,
        "date": selected_date,
        "date_to": date_to, "range": "upcoming" if upcoming else "day",
        "truncated": overflow or len(matches) > bounded_limit,
        "matches": [_match_summary(match) for match in matches[:bounded_limit]],
    }


def _match_in_preparation_window(match: dict, start: datetime, end: datetime) -> bool:
    """Keep dashboard coverage aligned with the scheduler's exact time window."""
    try:
        kickoff = preparation.kickoff(match)
    except (TypeError, ValueError):
        # A scheduled TBD may lack a usable kickoff; retain it by its declared
        # calendar date so the dashboard can explain why it is not researched.
        try:
            match_day = date.fromisoformat(str(match.get("date") or ""))
        except ValueError:
            return False
        return start.date() <= match_day <= end.date()
    return start < kickoff <= end


def get_match_desk(
    team_a: str, team_b: str, event: str = "", match_date: str = "today",
    match_time: str = "", match_format: str = "", game: str = "lol",
) -> dict:
    identity = normalize_match_identity({
        "team_a": team_a, "team_b": team_b, "event": event, "match_date": match_date,
        "match_time": match_time, "match_format": match_format, "game": game,
    })
    # 调用方没给时间（或缺省为“今天”）时，用数据库里的真实赛程补全日期/时间/赛制/赛事，
    # 避免把缺省值当成“今天 00:00”生成一个与真实赛程不符的幽灵场次。
    if not identity["match_time"]:
        schedule = repository.find_schedule_for_pair(identity["team_a"], identity["team_b"])
        if schedule:
            identity = normalize_match_identity({
                **identity,
                "match_date": schedule["date"] or identity["match_date"],
                "match_time": schedule["time_bjt"] or identity["match_time"],
                "match_format": schedule["format"] or identity["match_format"],
                "event": schedule["stage"] or identity["event"],
            })
    side_a = identity["team_a"]
    side_b = identity["team_b"]

    try:
        quantitative = {"available": True, **get_match_context(side_a, side_b, event=event)}
    except LookupError as exc:
        quantitative = {
            "available": False,
            "reason": str(exc),
            "boundary": "TS 底表暂缺，不影响读取其他已有单场、队伍和 TK 资料。",
        }
    team_a_evidence = _team_evidence(side_a)
    team_b_evidence = _team_evidence(side_b)
    framework = _match_trading_framework(identity, team_a_evidence, team_b_evidence)
    match_run = get_match_run(identity, framework=framework)
    from .collection import get_prepared_materials
    try:
        materials = get_prepared_materials(identity)
    except (OSError, ValueError):
        materials = {"task": None, "result": None, "notice": "比赛资料暂时无法读取，其他依据仍可查看。"}
    if match_run.get("mode") == "virtual_pre" and not match_run.get("result_unlocked"):
        materials = {"task": None, "result": None, "notice": "赛前回放不采用赛后收集资料。"}
    return {
        "match": _identity_payload(identity),
        "series_context": _series_context(identity),
        "quantitative": quantitative,
        "team_a": team_a_evidence,
        "team_b": team_b_evidence,
        "trading_framework": framework,
        "trade_plan": _trade_plan(identity, framework),
        "trading_notes": {
            "team_a": _trading_notes(side_a),
            "team_b": _trading_notes(side_b),
        },
        "boundary": "只汇总当前事实；方向、处理和变化条件由小雪在交易讨论中给出，不自动写交易或长期知识。",
        "workspace": get_match_workspace(identity),
        "match_run": match_run,
        "prepared_materials": materials,
    }


def _series_context(identity: dict) -> dict:
    """Describe how existing evidence is read for the scheduled series."""
    if str(identity.get("match_format") or "").upper() != "BO5":
        return {"format": identity.get("match_format") or "", "is_bo5": False, "items": []}
    return {
        "format": "BO5",
        "is_bo5": True,
        "title": "BO5 赛前资料",
        "items": [
            "常规赛 TS 是基础实力基线，后续系列赛结果只在其后连续校正。",
            "队伍画像与交易 TK 用来检查既有赢法在连续对抗中的适用条件。",
            "BP、首发和赛中变化出现后，只校正原赛前判断，不自动写入长期资料。",
        ],
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


def get_match_run(values: dict, *, framework: dict | None = None) -> dict:
    identity = _resolve_run_identity(values)
    row = repository.get_match_run_by_identity(identity)
    if not row:
        return {
            "exists": False,
            "match": _identity_payload(identity),
            "guide": _empty_run_guide(),
        }
    return _match_run_payload(row, framework=framework)


def get_active_match_run() -> dict:
    row = repository.get_active_match_run()
    if row and _run_has_finished_result(row):
        # Hide a finished session in this read projection; only explicit user
        # actions may change the saved activity state.
        row = None
    if not row or row["activity_status"] != "active":
        return {
            "exists": False,
            "guide": _empty_run_guide(),
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
        raise LookupError("沉淀候选不存在")
    return {"ok": True, "candidate": _knowledge_candidate_payload(row)}


def update_match_run_fact(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = _require_match_run(identity)
    try:
        fact_id = int(values.get("fact_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("要修改哪条依据不明确") from exc
    status = _limited_text(values.get("status"), "依据状态", 30).lower()
    label_to_status = {label: key for key, label in FACT_STATUS_LABELS.items()}
    status = label_to_status.get(status, status)
    if status not in FACT_STATUSES:
        options = "、".join(f"{key}（{label}）" for key, label in FACT_STATUS_LABELS.items())
        raise ValueError(f"依据状态只支持：{options}")
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
    cutoff_at = _cutoff_at(identity)
    schedule = repository.get_score_schedule(identity)
    score_match = {
        "schedule": _score_schedule_payload(schedule),
        "team_a_form": _score_form_payload(repository.list_score_team_form(identity["team_a"], cutoff_at), identity["team_a"]),
        "team_b_form": _score_form_payload(repository.list_score_team_form(identity["team_b"], cutoff_at), identity["team_b"]),
    }
    if view == "post":
        score_match["result"] = _score_result_payload(repository.get_score_result(identity))
    return {
        "match": _identity_payload(identity),
        "view": view,
        "source": "ScoreGG 导入库（只读）",
        "score_match": score_match,
        "boundary": "独立只读 ScoreGG 事实查询；不读取或改变任何交易推演状态。",
    }


def get_score_match_result(values: dict) -> dict:
    """Read one imported ScoreGG result without opening a trade run.

    Virtual-pre result sealing remains exclusive to ``get_score_match_evidence``.
    This public result lookup never creates, activates, unlocks, or changes a
    match run, workspace, trading note, or long-term knowledge.
    """
    identity = _resolve_run_identity(values)
    result = repository.get_score_result(identity)
    return {
        "match": _identity_payload(identity),
        "source": "ScoreGG 导入库（只读）",
        "result": _score_result_payload(result),
        "status": "completed" if result else "not_found",
        "boundary": "独立只读赛果查询；不读取或改变任何交易推演状态。",
    }


def get_gol_series_evidence(values: dict, game_id: int) -> dict:
    """Fetch an explicitly requested Gol.gg series without changing match state.

    Gol.gg has no stable public match-id mapping from ScoreGG, so callers pass
    a page id discovered from Gol.gg.  This avoids silently matching a similarly
    named historical series to the current event.
    """
    identity = _resolve_run_identity(values)
    evidence = gol_series_facts(game_id)
    observed = sorted({item.get("team") or "" for game in evidence.get("games", []) for item in game.get("teams", []) if item.get("team")})
    expected = {str(identity["team_a"]).casefold(), str(identity["team_b"]).casefold()}
    observed_folded = {item.casefold() for item in observed}
    conflict = bool(observed_folded and not expected.issubset(observed_folded))
    return {
        "status": "conflict" if conflict else "ok",
        "match": _identity_payload(identity),
        "source": "Gol.gg 公开逐局页面（按需只读）",
        "gol_series": evidence,
        "association": {
            "mode": "explicit_game_id", "observed_teams": observed,
            "conflict": conflict,
            "note": "Gol.gg 与 ScoreGG 没有可验证的统一比赛 ID；这是明确指定页面的局级事实，不自动写入或覆盖 ScoreGG。",
        },
        "boundary": "仅提供可追溯逐局事实；不改 TS、赛果正源、交易推演、TK 或长期资料。",
    }


def list_score_match_results(team: str = "", date_from: str = "", date_to: str = "", limit: int = 20) -> dict:
    """Read a bounded, filterable collection of completed ScoreGG results."""
    clean_team = _limited_text(team, "队伍", 40) if str(team or "").strip() else ""
    clean_from = _resolve_date(date_from) if str(date_from or "").strip() else ""
    clean_to = _resolve_date(date_to) if str(date_to or "").strip() else ""
    if clean_from and clean_to and clean_from > clean_to:
        raise ValueError("开始日期不能晚于结束日期")
    try:
        clean_limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    rows = repository.list_score_results(team=clean_team, date_from=clean_from, date_to=clean_to, limit=clean_limit)
    results = [{
        "match_id": row["match_id"], "team_a": row["team_a_id"], "team_b": row["team_b_id"],
        "winner": row["winner"], "score_a": row["score_a"], "score_b": row["score_b"],
        "match_time": row["match_time"], "event": row["league_id"], "format": row["game_format"],
        "stage": row["stage"], "updated_at": row["updated_at"],
    } for row in rows]
    return {
        "source": "ScoreGG 导入库（只读）", "filters": {
            "team": clean_team, "date_from": clean_from, "date_to": clean_to, "limit": clean_limit,
        }, "results": results, "status": "ok" if results else "empty",
        "boundary": "批量只读赛果查询；不读取或改变任何交易推演状态。",
    }


def get_match_run_review(values: dict) -> dict:
    identity = _resolve_run_identity(values)
    row = repository.get_match_run_by_identity(identity)
    if not row:
        return {
            "exists": False,
            "match": _identity_payload(identity),
            "reason": "这场没有赛前推演记录，无法进行推演复盘。",
            "score_evidence": get_score_match_evidence({**identity, "view": "post"}),
        }

    payload = _match_run_payload(row)
    payload["score_evidence"] = get_score_match_evidence({**identity, "view": "post"})
    return payload


def _run_has_finished_result(row) -> bool:
    if row["game"] != "lol":
        return False  # LOL results must never close another game's active run.
    cutoff_at = str(row["cutoff_at"] or "").strip()
    try:
        has_started = bool(cutoff_at) and datetime.fromisoformat(cutoff_at) <= datetime.now()
    except ValueError:
        has_started = False
    return has_started and repository.get_score_result(dict(row)) is not None


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
    if identity["game"] != "lol":
        return identity  # Never resolve another game's teams through LOL schedules.
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


def _kickoff_at(identity: dict):
    """真实开赛时刻；比赛时间未知时返回 None。

    不能用缺省 00:00 当作“已开赛”，否则当天还没排定时间的比赛会被误判为已开始并锁死空计划。
    """
    time_value = str(identity.get("match_time") or "").strip()
    if not time_value:
        return None
    try:
        return datetime.fromisoformat(f"{identity['match_date']} {time_value}:00")
    except ValueError:
        return None


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
    if identity.get("game", "lol") != "lol":
        return [{
            "fact_code": "E01", "kind": "qualitative", "label": "比赛资料缺口",
            "value": "尚未接入该游戏的自动赛程、首发、价格和赛果；不采用 LOL 数据",
            "source": "coverage", "source_ref": identity["game"], "as_of": "",
            "status": "missing", "affects": "情境应用",
            "action": "补充带来源和取得时间的本场依据；不承诺实时价格或后台监测。",
        }]
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
        starter_value = "、".join(f"{item['role']} {item['name']}" for item in starters) or "未取得登记名单"
        facts.append({
            "fact_code": f"E{base + 1:02d}", "kind": "qualitative", "label": f"{team} 登记名单",
            "value": starter_value, "source": "team_profile", "source_ref": team, "as_of": "",
            "status": "active" if starters else "missing",
            "affects": "阵容与对线", "action": "已登记选手可能包含轮换或替补，不代表本场首发；本场名单仍需核验。",
        })

        three_d = evidence.get("three_dimensional") or {}
        d3_value = "；".join(
            f"{item['label']}：{item['value']}" for item in (three_d.get("items") or []) if item.get("value")
        ) or three_d.get("version_understanding") or "未录入风格/版本理解"
        d3_status, d3_action = "active", _source_time_action(three_d.get("updated_at") or "")
        if not d3_value or d3_value == "未录入风格/版本理解":
            d3_status, d3_action = "missing", "补一条本场相关的风格或版本观察。"
        facts.append({
            "fact_code": f"E{base + 2:02d}", "kind": "qualitative", "label": f"{team} 风格 / 版本理解",
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

        form = repository.list_score_team_form(team, cutoff_at, match_format=identity["match_format"], league_id=identity["event"])
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


def _match_run_payload(row, *, framework: dict | None = None) -> dict:
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
        "trading_framework": framework if framework is not None else _match_trading_framework(identity),
        "revisions": [_run_revision_payload(item) for item in repository.list_match_run_revisions(row["id"])],
        "guide": _run_guide(row, facts), "updated_at": row["updated_at"],
        "debug_replay": {
            "enabled": row["mode"] == "virtual_pre",
            "result_available": bool(row["result_unlocked"]),
        },
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
    other_stage = bool(content and re.search(r"(?:世界赛|Worlds|S16)", str(config.get("event") or ""), re.I)
                       and re.search(r"第三赛段|(?:MSI|EWC).*预案", title, re.I)
                       and not re.search(r"世界赛|Worlds|S16", title, re.I))
    status = "historical" if other_stage else "ready" if content else "not_created"
    framework = {
        "status": status,
        "title": title or "当前赛段框架",
        "summary": _plan_summary(content) if content else "当前还没有可用的赛段框架。",
        "content": content,
        "updated_at": (plan or {}).get("updated_at", ""),
        "boundary": "这是其他赛事的历史预案，保留查阅，不作为本届当前框架。" if other_stage else "它是阶段背景，不是每场必须照抄；需要更新时再和小雪讨论并确认。",
    }
    return {
        "event": config.get("event", "当前赛事"),
        "leagues": config.get("leagues") or [],
        "preparation": config.get("preparation") or {"upcoming_days": 7},
        "confirmed_teams": config.get("confirmed_teams") or config.get("participants") or [],
        "participants_verified": config.get("participants_verified") is True,
        "participant_sources": config.get("participant_sources") or [],
        "aliases": config.get("aliases") or [],
        "source_hints": config.get("source_hints") or [],
        "team_aliases": config.get("team_aliases") or {},
        "phase": config.get("phase", ""),
        "knowledge_query": config.get("knowledge_query", config.get("event", "")),
        "plan_status": status,
        "plan_title": title,
        "plan_content": content,
        "plan_updated_at": (plan or {}).get("updated_at", ""),
        "plan_boundary": "完整预案只在与小雪确认后写入；工作台不自动生成。",
        "stage_framework": framework,
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
    if is_unresolved_matchup(team_a, team_b):
        raise ValueError("对阵未定：双方队伍尚未产生，不能作为具体比赛处理")
    game = _limited_text(values.get("game") or "lol", "项目", 20).lower()
    if game not in {"lol", "valorant", "cs2"}:
        raise ValueError("单场记录支持 lol、valorant、cs2")
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


PLACEHOLDER_TEAM_TOKENS = {"tbd", "tba", "待定", "未知", "n/a", "na", "-"}


def is_unresolved_matchup(team_a: str, team_b: str) -> bool:
    """对阵未定：赛程已排期但双方队伍还没产生（TBD 占位、缺一边或两边同名）。

    这类行是正常赛程数据（例如 S16 总决赛名额待定），不是错误数据；
    它们可以被列出，但不能进入任何需要真实对阵的链路。
    """
    left = str(team_a or "").strip().casefold()
    right = str(team_b or "").strip().casefold()
    if not left or not right:
        return True
    if left in PLACEHOLDER_TEAM_TOKENS or right in PLACEHOLDER_TEAM_TOKENS:
        return True
    return left == right


def _match_summary(match: dict) -> dict:
    team_a = str(match.get("team_a") or "").strip()
    team_b = str(match.get("team_b") or "").strip()
    if is_unresolved_matchup(team_a, team_b):
        return {
            "match": match,
            "pending": True,
            "pending_reason": "对阵未定：赛程已排期，双方队伍待产生",
            "ts": {"available": False, "reason": "对阵未定，暂不读取两队实力"},
            "trade_plan": None,
        }
    identity = normalize_match_identity({
        "team_a": team_a, "team_b": team_b, "event": match.get("stage") or match.get("region") or "",
        "match_date": match.get("date") or "today", "match_time": match.get("time") or "",
        "match_format": match.get("format") or "",
    })
    try:
        quantitative = get_match_context(team_a, team_b, event=match.get("stage") or match.get("region") or "")
        ts = {"available": True, **quantitative}
    except LookupError as exc:
        ts = {"available": False, "reason": str(exc)}
    return {
        "match": match, "pending": False, "ts": ts,
        "trade_plan": _trade_plan(identity, _match_trading_framework(identity)),
    }


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




def _parse_trade_plan_text(content: str, identity: dict) -> list[dict]:
    """Keep the first-slice text endpoint compatible without using it in the UI."""
    result: list[dict] = []
    text = str(content or "").strip()
    teams = (identity["team_a"], identity["team_b"])
    subject = next((team for team in teams if team.casefold() in text.casefold()), "本场")
    lowered = text.casefold()
    if "人头" in text and any(token in text for token in ("大", "多")):
        result.append({"market": "kills", "team": "", "direction": "做大", "statement": text})
    elif "人头" in text and any(token in text for token in ("小", "少")):
        result.append({"market": "kills", "team": "", "direction": "做小", "statement": text})
    elif ("时间" in text or "时长" in text) and any(token in text for token in ("大", "长", "久", "拖")):
        result.append({"market": "duration", "team": "", "direction": "做大", "statement": text})
    elif ("时间" in text or "时长" in text) and any(token in text for token in ("小", "短", "快")):
        result.append({"market": "duration", "team": "", "direction": "做小", "statement": text})
    elif any(token in lowered for token in ("做空", "看空", "发挥差", "容易送")):
        result.append({"market": "team", "team": subject, "direction": "做空", "statement": text})
    elif any(token in lowered for token in ("做多", "看多", "发挥好", "稳定", "变强", "强势")):
        result.append({"market": "team", "team": subject, "direction": "做多", "statement": text})
    return result


def save_trade_plan_manual(values: dict) -> dict:
    """Compatibility for an earlier text-only client; the current UI is structured."""
    identity = normalize_match_identity(values)
    content = _required_limited_text(values.get("content"), "本场补充", 500)
    parsed = _parse_trade_plan_text(content, identity)
    if not parsed:
        raise ValueError("本场补充请使用队伍做多/做空、人头做大/做小或时间做大/做小")
    plan = None
    for item in parsed:
        plan = create_trade_plan_item({**identity, **item, "statement": content})
    return plan or _trade_plan(identity, _match_trading_framework(identity))


def create_trade_plan_item(values: dict) -> dict:
    identity = normalize_match_identity(values)
    auto = _auto_trade_plan(_match_trading_framework(identity), identity)
    row = repository.get_trade_plan(identity["match_key"])
    plan = _trade_plan_from_row(identity, auto, row)
    _require_editable_trade_plan(plan)
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    item = _normalize_trade_plan_item(values, identity, item_id=f"manual-{uuid.uuid4().hex[:12]}", origin="manual")
    manual["items"].append(item)
    manual["order"] = _ordered_ids(plan["final"].get("items") or [], manual["order"])
    manual["order"].append(item["id"])
    return _store_draft_trade_plan(identity, auto, manual)


def update_trade_plan_item(values: dict) -> dict:
    identity = normalize_match_identity(values)
    item_id = _trade_plan_item_id(values.get("item_id"))
    auto = _auto_trade_plan(_match_trading_framework(identity), identity)
    row = repository.get_trade_plan(identity["match_key"])
    plan = _trade_plan_from_row(identity, auto, row)
    _require_editable_trade_plan(plan)
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    auto_item = next((item for item in auto["items"] if item["id"] == item_id), None)
    if auto_item:
        replacement = _normalize_trade_plan_item(values, identity, item_id=item_id, origin="auto", source=auto_item.get("source"))
        manual["overrides"][item_id] = {"mode": "replace", "item": replacement}
    else:
        index = next((index for index, item in enumerate(manual["items"]) if item["id"] == item_id), None)
        if index is None:
            raise LookupError("本场方案不存在")
        manual["items"][index] = _normalize_trade_plan_item(values, identity, item_id=item_id, origin="manual")
    return _store_draft_trade_plan(identity, auto, manual)


def delete_trade_plan_item(values: dict) -> dict:
    identity = normalize_match_identity(values)
    item_id = _trade_plan_item_id(values.get("item_id"))
    auto = _auto_trade_plan(_match_trading_framework(identity), identity)
    row = repository.get_trade_plan(identity["match_key"])
    plan = _trade_plan_from_row(identity, auto, row)
    _require_editable_trade_plan(plan)
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    if any(item["id"] == item_id for item in auto["items"]):
        manual["overrides"][item_id] = {"mode": "delete"}
    else:
        before = len(manual["items"])
        manual["items"] = [item for item in manual["items"] if item["id"] != item_id]
        if len(manual["items"]) == before:
            raise LookupError("本场方案不存在")
    manual["order"] = [value for value in manual["order"] if value != item_id]
    return _store_draft_trade_plan(identity, auto, manual)


def restore_trade_plan_item(values: dict) -> dict:
    identity = normalize_match_identity(values)
    item_id = _trade_plan_item_id(values.get("item_id"))
    auto = _auto_trade_plan(_match_trading_framework(identity), identity)
    row = repository.get_trade_plan(identity["match_key"])
    plan = _trade_plan_from_row(identity, auto, row)
    _require_editable_trade_plan(plan)
    if not any(item["id"] == item_id for item in auto["items"]):
        raise ValueError("只有自动方案可以恢复")
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    manual["overrides"].pop(item_id, None)
    return _store_draft_trade_plan(identity, auto, manual)


def reorder_trade_plan_item(values: dict) -> dict:
    identity = normalize_match_identity(values)
    item_id = _trade_plan_item_id(values.get("item_id"))
    movement = _limited_text(values.get("movement"), "排序方向", 10).lower()
    if movement not in {"up", "down"}:
        raise ValueError("排序方向只支持 up 或 down")
    auto = _auto_trade_plan(_match_trading_framework(identity), identity)
    row = repository.get_trade_plan(identity["match_key"])
    plan = _trade_plan_from_row(identity, auto, row)
    _require_editable_trade_plan(plan)
    current_ids = [item["id"] for item in plan["final"].get("items") or []]
    if item_id not in current_ids:
        raise LookupError("本场方案不存在或已删除")
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    order = _ordered_ids(plan["final"].get("items") or [], manual["order"])
    index = order.index(item_id)
    target = index - 1 if movement == "up" else index + 1
    if 0 <= target < len(order):
        order[index], order[target] = order[target], order[index]
    manual["order"] = order
    return _store_draft_trade_plan(identity, auto, manual)


def _trade_plan(identity: dict, framework: dict) -> dict:
    """Build the daily/individual pre-match plan from current TK, with no odds dependency."""
    auto = _auto_trade_plan(framework, identity)
    row = repository.get_trade_plan(identity["match_key"])
    return _trade_plan_from_row(identity, auto, row)


def _trade_plan_from_row(identity: dict, fresh_auto: dict, row) -> dict:
    """Project plans without writes; explicit editing stores the pre-match basis."""
    manual = _manual_trade_plan(row["manual_plan"] if row else {})
    now = datetime.now()
    kickoff = _kickoff_at(identity)
    started = bool(kickoff and kickoff <= now)
    raw_frozen = _json_object(row["frozen_plan"] if row else {})
    if row and (row["state"] == "locked" or raw_frozen):
        frozen = _frozen_trade_plan(raw_frozen)
        return _trade_plan_payload("locked", frozen["auto"], frozen["manual"], frozen["final"], frozen_at=frozen.get("frozen_at", ""), snapshot_missing=bool(frozen.get("snapshot_missing")))
    if started:
        if not row:
            frozen = {"auto": {"items": []}, "manual": _empty_manual_trade_plan(), "final": {"items": []}, "frozen_at": now.strftime("%Y-%m-%d %H:%M:%S"), "snapshot_missing": True}
        else:
            stored_auto = _auto_trade_plan_from_storage(row["auto_plan"])
            frozen_manual = manual
            frozen = {
                "auto": stored_auto,
                "manual": frozen_manual,
                "final": _compose_trade_plan(stored_auto, frozen_manual),
                "frozen_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            }
        return _trade_plan_payload("locked", frozen["auto"], frozen["manual"], frozen["final"], frozen_at=frozen["frozen_at"], snapshot_missing=bool(frozen.get("snapshot_missing")))
    final = _compose_trade_plan(fresh_auto, manual)
    return _trade_plan_payload("draft", fresh_auto, manual, final)


def _store_draft_trade_plan(identity: dict, auto: dict, manual: dict) -> dict:
    final = _compose_trade_plan(auto, manual)
    repository.upsert_trade_plan({**identity, "auto_plan": auto, "manual_plan": manual, "frozen_plan": {}, "state": "draft"})
    return _trade_plan_payload("draft", auto, manual, final)


def _auto_trade_plan(framework: dict, identity: dict) -> dict:
    """Related TK is research context, never an automatically adopted trade.

    Keep this composition seam for existing consumers. Historical frozen plans
    and explicitly saved user items retain their original read paths.
    """
    return {"items": []}


def _trade_plan_payload(state: str, auto: dict, manual: dict, final: dict, *, frozen_at: str = "", snapshot_missing: bool = False) -> dict:
    overrides = manual.get("overrides") or {}
    auto_items = []
    for base in auto.get("items") or []:
        item = dict(base)
        override = overrides.get(item.get("id"), {})
        item["manual_state"] = "deleted" if override.get("mode") == "delete" else ("edited" if override.get("mode") == "replace" else "automatic")
        if override.get("mode") == "replace":
            item["effective"] = dict(override.get("item") or {})
        auto_items.append(item)
    return {
        "state": state, "locked": state == "locked", "can_edit": state != "locked",
        "auto": {"items": auto_items}, "manual": {"items": manual.get("items") or []}, "final": final,
        "frozen_at": frozen_at, "snapshot_missing": snapshot_missing,
        "empty_reason": "没有可直接生成的交易 TK" if not auto_items else "",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _normalize_trade_plan_item(values: dict, identity: dict, *, item_id: str, origin: str, source: dict | None = None) -> dict:
    market = _limited_text(values.get("market"), "方案类型", 20).lower()
    if market not in PLAN_MARKETS:
        raise ValueError("方案类型只支持队伍、人头或时间")
    direction = _limited_text(values.get("direction"), "方案方向", 20)
    if direction not in PLAN_MARKETS[market]["directions"]:
        raise ValueError(f"{PLAN_MARKETS[market]['label']}方向不支持")
    team = _limited_text(values.get("team"), "队伍", 40).upper()
    if market == "team":
        if team not in {identity["team_a"], identity["team_b"]}:
            raise ValueError("队伍方案只能选择本场双方")
    else:
        team = ""
    statement = _limited_text(values.get("statement"), "说明", 240)
    return {"id": item_id, "origin": origin, "market": market, "team": team, "direction": direction, "statement": statement, "source": dict(source or {})}


def _trade_plan_item_id(value) -> str:
    item_id = _required_limited_text(value, "方案", 80)
    if not re.fullmatch(r"(?:auto|manual)-[A-Za-z0-9-]+", item_id):
        raise ValueError("方案标识无效")
    return item_id


def _require_editable_trade_plan(plan: dict) -> None:
    if plan.get("state") == "locked":
        raise ValueError("比赛已开始，赛前方案已锁定")


def get_trade_plan_review(values: dict) -> dict:
    identity = normalize_match_identity(values)
    plan = _trade_plan(identity, _match_trading_framework(identity))
    if plan["state"] != "locked":
        return {"status": "pre_match", "match": _identity_payload(identity), "plan": plan, "items": [], "tk_suggestions": [], "reason": "比赛尚未开始，赛后复盘会在最终赛前方案锁定后生成。"}
    if plan.get("snapshot_missing"):
        return {"status": "unavailable", "match": _identity_payload(identity), "plan": plan, "items": [], "tk_suggestions": [], "reason": "开赛前没有保存方案，无法把现在的交易 TK 当作当时使用的方案。"}
    result = _score_result_payload(repository.get_score_result(identity))
    if not result or result.get("status") != "completed":
        return {"status": "waiting_result", "match": _identity_payload(identity), "plan": plan, "result": result, "items": [], "tk_suggestions": [], "reason": "赛果尚未导入；不会猜测人头或时长结果。"}
    items = [_review_trade_plan_item(item, result) for item in plan["final"].get("items") or []]
    suggestions = [_tk_suggestion(item) for item in items if item.get("source", {}).get("tk_id")]
    return {
        "status": "ok", "match": _identity_payload(identity), "plan": plan, "result": result,
        "items": items, "tk_suggestions": suggestions,
        "boundary": "建议只供复盘；不会自动修改或删除任何长期交易 TK。",
    }


def _review_trade_plan_item(item: dict, result: dict) -> dict:
    reviewed = dict(item)
    if item.get("market") == "team":
        winner = str(result.get("winner") or "").upper()
        if not winner:
            outcome, reason = "no_data", "没有可靠队伍赛果"
        else:
            won = winner == item.get("team")
            matched = won if item.get("direction") == "做多" else not won
            outcome, reason = ("matched", "与系列赛赛果一致") if matched else ("missed", "与系列赛赛果相反")
    else:
        outcome, reason = "no_data", "没有可靠人头/时长赛果，未作猜测"
    reviewed["outcome"] = outcome
    reviewed["review_reason"] = reason
    return reviewed


def _tk_suggestion(item: dict) -> dict:
    if item.get("outcome") == "matched":
        recommendation, reason = "建议保留", "本场方向与赛果一致"
    elif item.get("outcome") == "missed":
        recommendation, reason = "建议删除", "本场方向与赛果相反"
    else:
        recommendation, reason = "暂不建议调整", item.get("review_reason") or "缺少可靠赛果"
    source = item.get("source") or {}
    return {"item_id": item.get("id"), "statement": source.get("statement") or item.get("statement") or "交易 TK", "recommendation": recommendation, "reason": reason}


def _match_trading_framework(identity: dict, team_a_evidence: dict | None = None, team_b_evidence: dict | None = None) -> dict:
    """Return only the already-recorded TK that can matter to this matchup.

    The list is deliberately separate from the stored match facts: editing a TK
    later should be visible when a paused match is reopened, without turning a
    reminder into an adopted trend inside the match thread.
    """
    if identity.get("game", "lol") != "lol":
        return {"available": False, "items": [], "boundary": "其他游戏 TK 从正式 TK 查询读取；不混用 LOL 画像与版本理解"}
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
    version_context = ""
    try:
        title = ((get_global_version_understanding().get("data") or {}).get("current_mainline") or {}).get("title") or ""
        match = re.search(r"\b(\d+\.\d+)\b", str(title))
        version_context = match.group(1) if match else ""
    except (LookupError, OSError, RuntimeError, ValueError, sqlite3.Error):
        pass
    return list_match_trading_tk(
        _event_region(identity.get("event") or ""), [side_a, side_b], players, limit=8,
        version_context=version_context,
    )


def _title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return "当前交易预案"


def _plan_summary(content: str) -> str:
    """Take a short human summary from the existing plan without rewriting its body."""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("##") and "核心判断" in line:
            candidates = []
            for candidate in lines[index + 1:]:
                stripped = candidate.strip()
                if stripped.startswith("##"):
                    break
                if not stripped or stripped.startswith(">") or stripped.startswith("-"):
                    continue
                candidates.append(stripped)
                if len(" ".join(candidates)) >= 180:
                    break
            if candidates:
                return " ".join(candidates)[:220]
    fallback = [line.strip(" -*#>") for line in lines if line.strip() and not line.strip().startswith(("#", ">", "-"))]
    return " ".join(fallback)[:220] or "当前赛段框架已建立，可展开查看全文。"
