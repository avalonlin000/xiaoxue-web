#!/usr/bin/env python3
"""Restricted Hermes MCP adapter for Xiaoxue's product API.

This adapter intentionally exposes only named Xiaoxue product operations. It
does not provide generic HTTP, filesystem, shell, database, cron, or cross-
profile access. Writes require the original user command to contain an
explicit TK-save phrase, while the product API remains the authority for team
validation, storage boundaries, and reindexing.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Literal
from urllib.parse import quote

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

PUBLIC_TOOL_FUNCTIONS = (
    "xiaoxue_get_today",
    "xiaoxue_find_schedules",
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


def _bounded_limit(value: int, *, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    return max(1, min(parsed, maximum))


async def _api_request(
    method: Literal["GET", "POST"],
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    if method not in {"GET", "POST"} or not endpoint.startswith("/"):
        raise ValueError("不允许的产品 API 操作")

    allowed_exact = {
        "/daily-content",
        "/schedules",
        "/teams",
        "/tk/search",
        "/market-notes",
        "/team-trading-notes",
    }
    allowed_patterns = (
        r"/profile-full/[^/]+",
        r"/version-understanding/[^/]+",
        r"/team-trading-notes/[^/]+",
        r"/tk/entry/[^/]+",
    )
    if endpoint not in allowed_exact and not any(re.fullmatch(pattern, endpoint) for pattern in allowed_patterns):
        raise ValueError("受限适配器不能访问该产品 API")
    if method == "POST" and endpoint != "/team-trading-notes":
        raise ValueError("受限适配器只允许写入队伍交易备注")

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
