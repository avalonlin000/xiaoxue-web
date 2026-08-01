#!/usr/bin/env python3
"""Restricted Hermes MCP adapter for Xiaoxue's product API.

This adapter intentionally exposes only named Xiaoxue product operations. It
does not provide generic HTTP, filesystem, shell, database, cron, or cross-
profile access. Writes require the original user command to contain an
explicit save phrase, while the product API remains the authority for team
validation, storage boundaries, and reindexing.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP


API_BASE_URL = os.getenv("XIAOXUE_API_BASE_URL", "http://127.0.0.1:8880/api").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_TEXT_CHARS = 12_000
EXPLICIT_TK_SAVE_PHRASES = (
    "记一下tk",
    "记一条tk",
    "记录tk",
    "保存tk",
    "存一下tk",
    "小雪记到",
    "记到",
)
EXPLICIT_MATCH_WORKSPACE_SAVE_PHRASES = (
    "留存当前判断",
    "保存当前判断",
    "更新当前判断",
    "记录这场变化",
    "记下这场变化",
)
MATCH_RUN_START_PHRASES = ("回顾", "重跑", "赛前", "准备", "分析", "看", "聊", "打开", "回到", "换看")
MATCH_RUN_PAUSE_PHRASES = ("先放", "暂存", "暂停", "先看别的", "换一场", "切换")
MATCH_RUN_ADVANCE_PHRASES = ("继续", "下一步", "进入", "往下")
MATCH_RUN_JUDGMENT_SAVE_PHRASES = ("保存赛前判断", "留存赛前判断", "记录赛前判断")
MATCH_RUN_UNLOCK_PHRASES = ("解封赛果", "开始复盘", "赛后复盘")
TRADING_TK_REMEMBER_PHRASES = ("帮我记着", "记着", "记下这条规律", "记录这条规律", "保存这条规律", "先记下来")
TRADING_TK_CONFIRM_PHRASES = ("确认这条规律", "这条规律成立", "按这条规律", "采用这条规律", "记下当前趋势", "确认这个趋势", "这就是趋势", "用这条规律")
TRADING_TK_INVALID_PHRASES = ("这条规律失效", "这条不成立", "标记失效", "不再采用")

PUBLIC_TOOL_FUNCTIONS = (
    "xiaoxue_get_today",
    "xiaoxue_find_schedules",
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
    "xiaoxue_remember_trading_tk",
    "xiaoxue_search_trading_tk",
    "xiaoxue_update_trading_tk",
    "xiaoxue_get_match_workspace",
    "xiaoxue_save_match_workspace",
    "xiaoxue_record_match_change",
    "xiaoxue_get_team",
    "xiaoxue_search_tk",
    "xiaoxue_get_tk_entry",
    "xiaoxue_list_market_notes",
    "xiaoxue_record_team_trading_note",
)

mcp = FastMCP("xiaoxue_product_mcp")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _clean_text(value: str, field: str, *, min_length: int = 1) -> str:
    clean = (value or "").strip()
    if len(clean) < min_length:
        raise ValueError(f"{field}不能为空")
    if len(clean) > MAX_TEXT_CHARS:
        raise ValueError(f"{field}过长")
    return clean


def _clean_team(value: str) -> str:
    clean = _clean_text(value, "队伍")
    if len(clean) > 40 or not re.fullmatch(r"[A-Za-z0-9._\-\u4e00-\u9fff ]+", clean):
        raise ValueError("队伍格式无效")
    return clean


def _require_explicit_tk_save(user_command: str) -> str:
    clean = _clean_text(user_command, "用户原始指令")
    normalized = re.sub(r"\s+", "", clean).lower()
    if not any(phrase in normalized for phrase in EXPLICIT_TK_SAVE_PHRASES):
        raise PermissionError("只有用户明确说“记一下 TK/保存 TK/小雪记到”时才能写入")
    return clean


def _require_explicit_match_workspace_save(user_command: str) -> str:
    clean = _clean_text(user_command, "用户原始指令")
    normalized = re.sub(r"\s+", "", clean).lower()
    if not any(phrase in normalized for phrase in EXPLICIT_MATCH_WORKSPACE_SAVE_PHRASES):
        raise PermissionError("只有用户明确说“留存/保存/更新当前判断”或“记录这场变化”时才能写入")
    return clean


def _require_phrase(user_command: str, phrases: tuple[str, ...], message: str) -> str:
    clean = _clean_text(user_command, "用户原始指令")
    normalized = re.sub(r"\s+", "", clean).lower()
    if not any(phrase in normalized for phrase in phrases):
        raise PermissionError(message)
    return clean


def _bounded_limit(value: int, *, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    return max(1, min(parsed, maximum))


def _resolve_command_match_date(user_command: str, supplied: str) -> str:
    """Resolve relative Chinese dates deterministically instead of trusting model arithmetic."""
    explicit = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", user_command or "")
    if explicit:
        return explicit.group(1)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    clean = user_command or ""
    if "前天" in clean:
        return (today - timedelta(days=2)).isoformat()
    if "昨天" in clean:
        return (today - timedelta(days=1)).isoformat()
    if "今天" in clean:
        return today.isoformat()
    return (supplied or "").strip()


async def _api_request(
    method: Literal["GET", "POST", "PUT", "PATCH"],
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    if method not in {"GET", "POST", "PUT", "PATCH"} or not endpoint.startswith("/"):
        raise ValueError("不允许的产品 API 操作")

    allowed_exact = {
        "/daily-content",
        "/schedules",
        "/teams",
        "/current-event/match-desk",
        "/current-event/match-run",
        "/current-event/match-run/active",
        "/current-event/match-runs",
        "/current-event/match-run/start",
        "/current-event/match-run/pause",
        "/current-event/match-run/entry",
        "/current-event/match-run/candidates",
        "/current-event/match-run/advance",
        "/current-event/match-run/judgment",
        "/current-event/match-run/unlock-result",
        "/current-event/match-run/review",
        "/current-event/score-evidence",
        "/current-event/match-workspace",
        "/current-event/match-workspace/changes",
        "/stage-review/candidates",
        "/trading-tk",
        "/tk/search",
        "/market-notes",
        "/team-trading-notes",
    }
    allowed_patterns = (
        r"/profile-full/[^/]+",
        r"/version-understanding/[^/]+",
        r"/team-trading-notes/[^/]+",
        r"/tk/entry/[^/]+",
        r"/current-event/match-run/facts/\d+",
        r"/stage-review/candidates/\d+",
        r"/trading-tk/[^/]+\.md",
    )
    if endpoint not in allowed_exact and not any(re.fullmatch(pattern, endpoint) for pattern in allowed_patterns):
        raise ValueError("受限适配器不能访问该产品 API")
    write_operations = {
        ("POST", "/team-trading-notes"),
        ("PUT", "/current-event/match-workspace"),
        ("POST", "/current-event/match-workspace/changes"),
        ("POST", "/current-event/match-run/start"),
        ("POST", "/current-event/match-run/pause"),
        ("PUT", "/current-event/match-run/entry"),
        ("POST", "/current-event/match-run/candidates"),
        ("POST", "/current-event/match-run/advance"),
        ("PUT", "/current-event/match-run/judgment"),
        ("POST", "/current-event/match-run/unlock-result"),
        ("POST", "/trading-tk"),
    }
    if method == "PUT" and re.fullmatch(r"/current-event/match-run/facts/\d+", endpoint):
        write_operations.add((method, endpoint))
    if method == "PATCH" and (
        re.fullmatch(r"/stage-review/candidates/\d+", endpoint)
        or re.fullmatch(r"/trading-tk/[^/]+\.md", endpoint)
    ):
        write_operations.add((method, endpoint))
    if method != "GET" and (method, endpoint) not in write_operations:
        raise ValueError("受限适配器不允许该写入操作")

    try:
        async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.request(method, endpoint, params=params, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError("小雪工作台响应超时；本次没有写入") from exc
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            body = exc.response.json()
            detail = str(body.get("detail", "")) if isinstance(body, dict) else ""
        except (TypeError, ValueError):
            pass
        suffix = f"：{detail}" if detail else ""
        raise RuntimeError(f"小雪工作台拒绝操作（{exc.response.status_code}）{suffix}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("小雪工作台当前不可用；本次没有写入") from exc


@mcp.tool(
    name="xiaoxue_get_today",
    annotations={"title": "读取小雪今日入口", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_today(date: str = "today") -> str:
    """读取指定日期的赛程与今日内容状态；“今天什么比赛”优先使用。"""

    clean_date = (date or "today").strip() or "today"
    return _json(await _api_request("GET", "/daily-content", params={"date": clean_date}))


@mcp.tool(
    name="xiaoxue_find_schedules",
    annotations={"title": "查询小雪赛程", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_find_schedules(
    team: str = "",
    date_from: str = "",
    date_to: str = "",
    upcoming: bool = False,
    limit: int = 20,
) -> str:
    """按队伍和日期范围查询正式赛程数据。"""

    params: dict[str, Any] = {"limit": _bounded_limit(limit), "upcoming": bool(upcoming)}
    if team.strip():
        params["team"] = _clean_team(team)
    if date_from.strip():
        params["date_from"] = date_from.strip()
    if date_to.strip():
        params["date_to"] = date_to.strip()
    return _json(await _api_request("GET", "/schedules", params=params))


@mcp.tool(
    name="xiaoxue_prepare_match",
    annotations={"title": "汇总单场交易底稿", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_prepare_match(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """读取一场比赛的 TS、首发、三维和交易 TK；只汇总事实，不替用户写交易或长期知识。"""

    params: dict[str, Any] = {"team_a": _clean_team(team_a), "team_b": _clean_team(team_b)}
    if event.strip():
        params["event"] = _clean_text(event, "赛事")
    if match_date.strip():
        params["match_date"] = _clean_text(match_date, "比赛日期")
    if match_time.strip():
        params["match_time"] = _clean_text(match_time, "比赛时间")
    if match_format.strip():
        params["match_format"] = _clean_text(match_format, "赛制")
    return _json(await _api_request("GET", "/current-event/match-desk", params=params))


def _match_params(
    team_a: str,
    team_b: str,
    *,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {"team_a": _clean_team(team_a), "team_b": _clean_team(team_b)}
    if event.strip():
        params["event"] = _clean_text(event, "赛事")
    if match_date.strip():
        params["match_date"] = _clean_text(match_date, "比赛日期")
    if match_time.strip():
        params["match_time"] = _clean_text(match_time, "比赛时间")
    if match_format.strip():
        params["match_format"] = _clean_text(match_format, "赛制")
    return params


def _match_payload(
    team_a: str,
    team_b: str,
    *,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> dict[str, Any]:
    return {"game": "lol", **_match_params(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )}


@mcp.tool(
    name="xiaoxue_start_match_run",
    annotations={"title": "打开或恢复单场交易推演", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_start_match_run(
    user_command: str,
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
    mode: str = "live",
    focus: str = "",
) -> str:
    """打开、切换或恢复一场临时交易推演；可直接指定要看的模块，另一场自动暂存。"""

    _require_phrase(user_command, MATCH_RUN_START_PHRASES, "用户明确说要看、聊、打开、回到或切换这场后才能建立临时推演")
    resolved_date = _resolve_command_match_date(user_command, match_date)
    payload = {**_match_payload(team_a, team_b, event=event, match_date=resolved_date, match_time=match_time, match_format=match_format),
               "mode": _clean_text(mode, "运行模式")}
    if focus.strip():
        payload["focus"] = _clean_text(focus, "当前模块")
    result = await _api_request("POST", "/current-event/match-run/start", payload=payload)
    return _json(_first_turn_run_summary(result))


@mcp.tool(
    name="xiaoxue_get_match_run",
    annotations={"title": "读取一场临时交易推演", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_match_run(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """读取这场已保存的交易环节、调用依据和当前模块；不要求按顺序继续。"""

    return _json(await _api_request("GET", "/current-event/match-run", params=_match_params(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_get_active_match_trade",
    annotations={"title": "读取当前正在聊的比赛", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_active_match_trade() -> str:
    """用户说继续但没有重复队名时，读取当前正在讨论的单场交易推演。"""

    return _json(await _api_request("GET", "/current-event/match-run/active"))


@mcp.tool(
    name="xiaoxue_pause_match_trade",
    annotations={"title": "暂存并放下当前比赛", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_pause_match_trade(
    user_command: str,
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """用户说先放下、暂停或切换时暂存当前比赛；不会标记完成。"""

    _require_phrase(user_command, MATCH_RUN_PAUSE_PHRASES, "用户明确说先放下、暂停或切换比赛后才能暂存")
    return _json(await _api_request("POST", "/current-event/match-run/pause", payload=_match_payload(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_save_match_trade_entry",
    annotations={"title": "更新单场交易推演的一项", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_save_match_trade_entry(
    user_command: str,
    team_a: str,
    team_b: str,
    section: Literal["version", "team", "trend", "matchup", "lineup", "branches", "market", "plan", "entry", "exit", "execution", "review"],
    content: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """保存用户当轮正在讨论的一个交易环节；可跳着写，只改这一项，不写长期知识。"""

    _clean_text(user_command, "用户原始指令")
    confirmed_by_user = False
    if section == "trend":
        _require_phrase(
            user_command,
            TRADING_TK_CONFIRM_PHRASES,
            "只有用户明确确认、采用或要求记下这条趋势后，才能写入本场已采用规律",
        )
        confirmed_by_user = True
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "section": section,
        "content": _clean_text(content, "当前交易判断"),
        "confirmed_by_user": confirmed_by_user,
    }
    return _json(await _api_request("PUT", "/current-event/match-run/entry", payload=payload))


@mcp.tool(
    name="xiaoxue_update_match_run_fact",
    annotations={"title": "修正一条比赛依据", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_update_match_run_fact(
    user_command: str,
    team_a: str,
    team_b: str,
    fact_id: int,
    status: str,
    value: str,
    reason: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """按用户当轮明确的纠正，更新且只更新一条依据，并保留修改原因。"""

    _clean_text(user_command, "用户原始指令")
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "fact_id": int(fact_id), "status": _clean_text(status, "依据状态"),
        "value": _clean_text(value, "依据内容"), "reason": _clean_text(reason, "修改原因"),
    }
    return _json(await _api_request("PUT", f"/current-event/match-run/facts/{int(fact_id)}", payload=payload))


@mcp.tool(
    name="xiaoxue_advance_match_run",
    annotations={"title": "推进单场流程", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_advance_match_run(
    user_command: str,
    team_a: str,
    team_b: str,
    phase: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """在用户说继续/下一步后推进一阶段；不会跳到未解封的赛后复盘。"""

    _require_phrase(user_command, MATCH_RUN_ADVANCE_PHRASES, "用户明确说继续、下一步或进入后才能推进流程")
    payload = {**_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
               "phase": _clean_text(phase, "流程阶段")}
    return _json(await _api_request("POST", "/current-event/match-run/advance", payload=payload))


@mcp.tool(
    name="xiaoxue_save_virtual_judgment",
    annotations={"title": "留存赛前虚拟判断", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_save_virtual_judgment(
    user_command: str,
    team_a: str,
    team_b: str,
    direction: str,
    reasons: str,
    handling: str,
    change_conditions: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """只在用户明确要求留存赛前判断时写入四行虚拟判断，不写长期 TK。"""

    _require_phrase(user_command, MATCH_RUN_JUDGMENT_SAVE_PHRASES, "只有用户明确说保存/留存赛前判断时才能写入")
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "direction": _clean_text(direction, "方向"), "reasons": _clean_text(reasons, "理由"),
        "handling": _clean_text(handling, "处理"), "change_conditions": _clean_text(change_conditions, "变化条件"),
    }
    return _json(await _api_request("PUT", "/current-event/match-run/judgment", payload=payload))


@mcp.tool(
    name="xiaoxue_get_score_evidence",
    annotations={"title": "读取 ScoreGG 比赛证据", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_score_evidence(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
    view: str = "pre",
) -> str:
    """读取本地 ScoreGG 导入证据；正常比赛复盘可直接读 post，历史调试才使用赛果隐藏开关。"""

    params = _match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format)
    params["view"] = _clean_text(view, "查看阶段")
    return _json(await _api_request("GET", "/current-event/score-evidence", params=params))


@mcp.tool(
    name="xiaoxue_unlock_match_result",
    annotations={"title": "解封赛果进入复盘", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_unlock_match_result(
    user_command: str,
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """用户明确说解封赛果/开始复盘后，才允许进入赛后资料和复盘。"""

    _require_phrase(user_command, MATCH_RUN_UNLOCK_PHRASES, "只有用户明确说“解封赛果”或“开始复盘”时才能查看赛后结果")
    return _json(await _api_request("POST", "/current-event/match-run/unlock-result", payload=_match_payload(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_debug_reveal_match_result",
    annotations={"title": "历史回放测试读取赛果", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_debug_reveal_match_result(
    user_command: str,
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """仅在历史回放调试中，用户完成虚拟赛前判断后读取真实赛果。"""

    _require_phrase(
        user_command,
        ("查看测试赛果", "公布测试赛果", "回放测试复盘"),
        "只有历史回放调试完成赛前判断后才能读取测试赛果",
    )
    return _json(await _api_request("POST", "/current-event/match-run/unlock-result", payload=_match_payload(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_get_match_run_review",
    annotations={"title": "读取单场赛后复盘底稿", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_match_run_review(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """读取已保存的单场推演、依据修订和 ScoreGG 赛后结果，供复盘并提炼实体候选。"""

    return _json(await _api_request("GET", "/current-event/match-run/review", params=_match_params(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


def _first_turn_run_summary(result: dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    """Keep the first chat turn small and hide internal fact identifiers."""
    if not isinstance(result, dict):
        return result
    facts = result.get("facts")
    if not isinstance(facts, list):
        return result
    selected: list[dict[str, Any]] = []
    schedule = next((item for item in facts if item.get("source") == "scoregg_schedule"), None)
    if schedule:
        selected.append(schedule)
    framework = result.get("trading_framework") or {}
    framework_items = framework.get("items") if isinstance(framework, dict) else []
    if not isinstance(framework_items, list):
        framework_items = []
    relevant_tk = [
        {
            "scope": item.get("scope"),
            "scope_label": item.get("scope_label"),
            "statement": item.get("statement"),
            "status": item.get("status"),
        }
        for item in framework_items[:4]
        if isinstance(item, dict) and item.get("statement")
    ]
    match = result.get("match") or {}
    focus = result.get("focus") or "overview"
    focus_label = {
        "overview": "单场底稿", "version": "版本与环境", "team": "队伍与选手",
        "trend": "已采用规律", "matchup": "本场适用性", "lineup": "阵容条件",
        "branches": "条件分支", "market": "市场对照", "plan": "当前交易计划",
        "entry": "入场信号", "exit": "退出条件", "execution": "实际执行", "review": "复盘结论",
    }.get(focus, result.get("guide", {}).get("focus_label") or focus)
    summary = {
        "match": match,
        "focus": focus,
        "facts": selected,
        "guide": result.get("guide"),
        "trading_framework": {
            "call_order": framework.get("call_order") or ["全局", "赛区", "队伍/选手"],
            "items": relevant_tk,
            "boundary": "只作本场提醒；是否采用由钧钧确认。",
        },
        "reply_contract": {
            "start": f"当前：{match.get('team_a', '')} vs {match.get('team_b', '')}｜正在看：{focus_label}",
            "shape": "判断 / 依据 / 可接模块（仅在有必要时）",
            "rules": ["按钧钧当轮指定模块开始", "不强推版本", "不得自行确认趋势", "最多两条精炼依据", "能直接回答就结束，不强塞下一步", "不以问题结尾"],
        },
    }
    if result.get("mode") == "virtual_pre":
        summary["debug_replay"] = True
    return summary


@mcp.tool(
    name="xiaoxue_remember_trading_tk",
    annotations={"title": "记录一条待验证交易 TK", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_remember_trading_tk(
    user_command: str,
    statement: str,
    category: Literal["version", "regional_style", "team_style", "player_style", "roster", "lineup", "market", "execution", "general"] = "general",
    context: str = "",
    scope: Literal["global", "region", "team", "player"] = "global",
    region: str = "",
    subject: str = "",
    version_context: str = "",
) -> str:
    """用户明确说帮我记着时，按全局、赛区、队伍或选手写入同一 TK 资料库；不自动升级为已确认趋势。"""

    clean_command = _require_phrase(
        user_command,
        TRADING_TK_REMEMBER_PHRASES,
        "只有用户明确说帮我记着、记下或保存这条规律后才能写入",
    )
    return _json(await _api_request("POST", "/trading-tk", payload={
        "category": category,
        "statement": _clean_text(statement, "规律内容"),
        "context": (context or "").strip(),
        "scope": scope,
        "region": (region or "").strip(),
        "subject": (subject or "").strip(),
        "version_context": (version_context or "").strip(),
        "source_command": clean_command,
    }))


@mcp.tool(
    name="xiaoxue_search_trading_tk",
    annotations={"title": "搜索通用交易 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_search_trading_tk(
    query: str = "",
    status: Literal["candidate", "confirmed", "invalid", "all"] = "all",
    scope: Literal["global", "region", "team", "player", "all"] = "all",
    region: str = "",
    subject: str = "",
    version_context: str = "",
    limit: int = 30,
) -> str:
    """从原有 TK 资料库找回全局、赛区、队伍或选手交易 TK；待验证、已确认和已失效必须明确区分。"""

    return _json(await _api_request("GET", "/trading-tk", params={
        "q": (query or "").strip(), "status": status, "scope": scope,
        "region": (region or "").strip(), "subject": (subject or "").strip(),
        "version_context": (version_context or "").strip(), "limit": _bounded_limit(limit, maximum=100),
    }))


@mcp.tool(
    name="xiaoxue_update_trading_tk",
    annotations={"title": "确认或停用交易 TK", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_update_trading_tk(
    user_command: str,
    filename: str,
    status: Literal["confirmed", "invalid"],
    review_note: str = "",
) -> str:
    """只按用户明确复查结论，更新原交易 TK 词条的状态；不复制、不删除历史。"""

    phrases = TRADING_TK_CONFIRM_PHRASES if status == "confirmed" else TRADING_TK_INVALID_PHRASES
    _require_phrase(user_command, phrases, "只有用户明确确认规律成立或失效后才能修改状态")
    clean_filename = _clean_text(filename, "交易 TK 文件名")
    if not re.fullmatch(r"trading_tk_(?:general|global|region|team|player)_[a-f0-9]{16}\.md", clean_filename):
        raise ValueError("交易 TK 文件名无效")
    return _json(await _api_request("PATCH", f"/trading-tk/{quote(clean_filename, safe='')}", payload={
        "status": status, "review_note": (review_note or "").strip(),
    }))


@mcp.tool(
    name="xiaoxue_add_stage_candidate",
    annotations={"title": "把新认识放入阶段整理", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_add_stage_candidate(
    user_command: str,
    team_a: str,
    team_b: str,
    target_type: Literal["team", "player", "version", "trading_method"],
    target_name: str,
    topic: str,
    observation: str,
    reason: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """仅在本场产生具体新认识时加入阶段整理；不直接修改队伍、选手、版本或交易方法。"""

    _clean_text(user_command, "用户原始指令")
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "target_type": target_type,
        "target_name": (target_name or "").strip(),
        "topic": _clean_text(topic, "更新主题"),
        "observation": _clean_text(observation, "新观察"),
        "reason": _clean_text(reason, "为什么值得整理"),
    }
    return _json(await _api_request("POST", "/current-event/match-run/candidates", payload=payload))


@mcp.tool(
    name="xiaoxue_list_stage_candidates",
    annotations={"title": "读取阶段整理候选", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_list_stage_candidates(status: Literal["pending", "ignored", "applied"] = "pending", limit: int = 100) -> str:
    """阶段知识整理开始时读取按队伍、选手、版本和交易方法归属的候选。"""

    return _json(await _api_request("GET", "/stage-review/candidates", params={
        "status": status,
        "limit": _bounded_limit(limit, maximum=200),
    }))


@mcp.tool(
    name="xiaoxue_update_stage_candidate",
    annotations={"title": "更新阶段整理候选状态", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_update_stage_candidate(user_command: str, candidate_id: int, status: Literal["ignored", "applied"]) -> str:
    """用户决定本轮不处理，或长期正源已确认写回并读回后，更新候选状态。"""

    _clean_text(user_command, "用户原始指令")
    return _json(await _api_request("PATCH", f"/stage-review/candidates/{int(candidate_id)}", payload={"status": status}))


@mcp.tool(
    name="xiaoxue_get_match_workspace",
    annotations={"title": "读取单场当前判断", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_match_workspace(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """读取某场已留存的四行判断及其后续具体变化；没有记录时明确返回空工作台。"""

    return _json(await _api_request(
        "GET", "/current-event/match-workspace",
        params=_match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
    ))


@mcp.tool(
    name="xiaoxue_save_match_workspace",
    annotations={"title": "留存单场当前判断", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_save_match_workspace(
    user_command: str,
    team_a: str,
    team_b: str,
    direction: str,
    reasons: str,
    handling: str,
    change_conditions: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """只在用户明确要求留存时，写入本场四行当前判断；不会写 TK、画像、三维或盘口记录。"""

    _require_explicit_match_workspace_save(user_command)
    payload = {
        "game": "lol",
        **_match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "direction": _clean_text(direction, "方向"),
        "reasons": _clean_text(reasons, "理由"),
        "handling": _clean_text(handling, "处理"),
        "change_conditions": _clean_text(change_conditions, "变化条件"),
    }
    return _json(await _api_request("PUT", "/current-event/match-workspace", payload=payload))


@mcp.tool(
    name="xiaoxue_record_match_change",
    annotations={"title": "记录单场具体变化", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_record_match_change(
    user_command: str,
    team_a: str,
    team_b: str,
    source: str,
    impact: str,
    detail: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """只在用户明确要求记录时，追加一条具体变化；不自动改写这场当前判断。"""

    _require_explicit_match_workspace_save(user_command)
    payload = {
        "game": "lol",
        **_match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "source": _clean_text(source, "变化来源"),
        "impact": _clean_text(impact, "影响"),
        "detail": _clean_text(detail, "变化内容"),
    }
    return _json(await _api_request("POST", "/current-event/match-workspace/changes", payload=payload))


@mcp.tool(
    name="xiaoxue_get_team",
    annotations={"title": "读取小雪队伍资料", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_team(team: str, trading_note_limit: int = 8) -> str:
    """一次读取队伍画像、版本理解和已确认的队伍交易备注。"""

    clean_team = _clean_team(team)
    encoded = quote(clean_team, safe="")
    profile, version, notes = await asyncio.gather(
        _api_request("GET", f"/profile-full/{encoded}"),
        _api_request("GET", f"/version-understanding/{encoded}"),
        _api_request(
            "GET",
            f"/team-trading-notes/{encoded}",
            params={"status": "active", "limit": _bounded_limit(trading_note_limit, maximum=20)},
        ),
    )
    return _json({"team": clean_team, "profile": profile, "version_understanding": version, "trading_notes": notes})


@mcp.tool(
    name="xiaoxue_search_tk",
    annotations={"title": "搜索小雪 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_search_tk(query: str, team: str = "", limit: int = 10) -> str:
    """通过工作台正式 TK 搜索入口检索，不扫描文件系统。"""

    params: dict[str, Any] = {"q": _clean_text(query, "查询词"), "limit": _bounded_limit(limit, maximum=20)}
    if team.strip():
        params["team"] = _clean_team(team)
    return _json(await _api_request("GET", "/tk/search", params=params))


@mcp.tool(
    name="xiaoxue_get_tk_entry",
    annotations={"title": "读取一条小雪 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_get_tk_entry(filename: str) -> str:
    """读取 TK 搜索结果中的一条正式正文。"""

    clean = _clean_text(filename, "TK 文件名")
    if "/" in clean or "\\" in clean or clean in {".", ".."}:
        raise ValueError("TK 文件名无效")
    return _json(await _api_request("GET", f"/tk/entry/{quote(clean, safe='')}"))


@mcp.tool(
    name="xiaoxue_list_market_notes",
    annotations={"title": "读取小雪盘口记录", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def xiaoxue_list_market_notes(limit: int = 10) -> str:
    """只读列出当前 LOL 盘口/交易判断记录。"""

    return _json(await _api_request("GET", "/market-notes", params={"game": "lol", "limit": _bounded_limit(limit, maximum=30)}))


@mcp.tool(
    name="xiaoxue_record_team_trading_note",
    annotations={"title": "记录小雪队伍交易 TK", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def xiaoxue_record_team_trading_note(
    user_command: str,
    team: str,
    note: str,
    title: str = "",
    market: str = "",
    scenario: str = "",
) -> str:
    """用户明确说“记一下 TK/小雪记到”时，把原话写入明确队伍的 TK。"""

    _require_explicit_tk_save(user_command)
    payload = {
        "team": _clean_team(team),
        "note": _clean_text(note, "TK 内容", min_length=4),
        "title": (title or "").strip(),
        "market": (market or "").strip(),
        "scenario": (scenario or "").strip(),
        "status": "active",
    }
    return _json(await _api_request("POST", "/team-trading-notes", payload=payload))


if __name__ == "__main__":
    mcp.run()
