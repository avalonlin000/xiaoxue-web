#!/usr/bin/env python3
"""Restricted Hermes MCP adapter for Xiaoxue's product API.

This adapter intentionally exposes only named Xiaoxue product operations. It
does not provide generic HTTP, filesystem, shell, database, cron, or cross-
profile access. Xiaoxue's root Skill classifies semantic intent and passes the
original user command as audit evidence. This adapter validates payloads,
side-effect boundaries, and product API contracts without matching magic
phrases in the user's wording.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import secrets
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import httpx
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from fastmcp import FastMCP

# 统一配置：端口/URL 从 lol_data/config/system_config.json 读取，禁止硬编码
_LOL_LIBS = Path("/home/ubuntu/lol_data/libs")
if str(_LOL_LIBS) not in sys.path:
    sys.path.insert(0, str(_LOL_LIBS))
from config import get_service_url  # noqa: E402

API_BASE_URL = os.getenv("XIAOXUE_API_BASE_URL", get_service_url("workbench_api_url") + "/api").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 20.0
EXTERNAL_SEARCH_TIMEOUT_SECONDS = 25.0
EXTERNAL_NEWS_MAX_RECENCY_DAYS = 30
EXTERNAL_NEWS_MAX_RESULTS = 8
MCPORTER_PATH = "/home/ubuntu/.npm-global/bin/mcporter"
HERMES_PYTHON_PATH = "/home/ubuntu/.hermes/hermes-agent/venv/bin/python"
HERMES_AGENT_ROOT = "/home/ubuntu/.hermes/hermes-agent"
MAX_TEXT_CHARS = 12_000


mcp = FastMCP("xiaoxue_product_mcp")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _read_result(data: Any, *, capability: str, version: str, summary: str, source: str) -> dict[str, Any]:
    """Wrap migrated read tools in the common result envelope."""

    status = "ok"
    if data is None or data == [] or data == {}:
        status = "empty"
    elif isinstance(data, dict):
        for key in ("results", "items", "schedules", "updates"):
            if key in data and isinstance(data[key], list) and not data[key]:
                status = "empty"
                break
    result = {
        "status": status,
        "summary": summary if status == "ok" else f"{summary}：当前没有结果",
        "data": data,
        "sources": [{"kind": "xiaoxue_api", "path": source}],
        "effects": {"effect": "read", "network": False, "writes": []},
        "readback": None,
        "gaps": [] if status == "ok" else ["当前正式入口没有匹配结果"],
        "conflicts": [],
        "error": None,
        "trace": {"capability": capability, "version": version},
    }
    # Dict-shaped legacy MCP responses keep their original top-level fields
    # during migration; new consumers use the stable envelope and `data`.
    if isinstance(data, dict):
        for key, value in data.items():
            result.setdefault(key, value)
    return result


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


def _bounded_limit(value: int, *, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    return max(1, min(parsed, maximum))


def _bounded_days(value: int, *, maximum: int = 365) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("days 必须是整数") from exc
    return max(1, min(parsed, maximum))


TK_SEARCH_SNIPPET_CHARS = 300


def _slim_tk_search(data: Any) -> Any:
    """TK 搜索结果只回片段；全文用 xiaoxue_get_tk_entry 读取。"""
    if not isinstance(data, dict):
        return data
    results = data.get("results")
    if not isinstance(results, list):
        return data
    slimmed: list[Any] = []
    for item in results:
        if isinstance(item, dict):
            copy = dict(item)
            content = copy.get("content")
            if isinstance(content, str) and len(content) > TK_SEARCH_SNIPPET_CHARS:
                copy["content"] = content[:TK_SEARCH_SNIPPET_CHARS] + "…（已截断；全文可用 xiaoxue_get_tk_entry 读取）"
            slimmed.append(copy)
        else:
            slimmed.append(item)
    out = dict(data)
    out["results"] = slimmed
    return out


FIRST_TURN_TK_ITEM_KEYS = ("scope", "scope_label", "subject", "statement", "context")


def _slim_first_turn_brief(brief: Any, *, drop_guide: bool) -> Any:
    """首轮资料包瘦身：去掉与主回执重复的 guide 结构，规律条目只保留提醒所需字段。"""
    if not isinstance(brief, dict):
        return brief
    out = dict(brief)
    facts = out.get("match_facts")
    if not isinstance(facts, dict):
        return out
    facts = dict(facts)
    match_run = facts.get("match_run")
    if drop_guide and isinstance(match_run, dict):
        match_run = dict(match_run)
        match_run.pop("guide", None)
        facts["match_run"] = match_run
    framework = facts.get("trading_framework")
    if isinstance(framework, dict) and isinstance(framework.get("items"), list):
        framework = dict(framework)
        framework["items"] = [
            {k: item.get(k) for k in FIRST_TURN_TK_ITEM_KEYS if item.get(k) not in (None, "", [])}
            if isinstance(item, dict) else item
            for item in framework["items"]
        ]
        facts["trading_framework"] = framework
    out["match_facts"] = facts
    return out


def _save_entry_ack(result: Any, *, section: str) -> dict:
    """单场推演写入回执：只回确认与轻量字段，不重传全量 run。"""
    ack: dict[str, Any] = {"status": "ok", "action": "已保存单场推演环节", "section": section}
    if isinstance(result, dict):
        for key in ("focus", "activity_status", "updated_at"):
            value = result.get(key)
            if value not in (None, "", [], {}):
                ack[key] = value
    return ack


DESTRUCTIVE_MUTATION_MARKERS = (
    "delete", "remove", "clear_all", "clear_table", "delete_all", "bulk_delete",
    "bulk_overwrite", "migrate", "replace_source", "清空", "删除", "批量覆盖", "迁移", "换正源",
)


def _assert_safe_mutation(endpoint: str, payload: dict[str, Any] | None) -> None:
    """Keep irreversible text/data deletion blocked while allowing ordinary writes."""
    lower_endpoint = endpoint.casefold()
    if any(marker in lower_endpoint for marker in DESTRUCTIVE_MUTATION_MARKERS):
        raise ValueError("删除、清空、批量覆盖、迁移或换正源仍需钧钧单独确认")
    operation = str((payload or {}).get("operation") or "").casefold()
    if any(marker in operation for marker in DESTRUCTIVE_MUTATION_MARKERS):
        raise ValueError("删除、清空、批量覆盖、迁移或换正源仍需钧钧单独确认")


def _positive_id(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}必须是整数") from exc
    if parsed < 1:
        raise ValueError(f"{field}必须大于 0")
    return parsed


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


def _bounded_external_news_recency(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("recency_days 必须是整数") from exc
    return max(1, min(parsed, EXTERNAL_NEWS_MAX_RECENCY_DAYS))


def _external_news_search_query(query: str, after: str) -> str:
    return f"League of Legends esports {query} latest news after {after}"


def _run_exa_search(query: str, limit: int) -> str:
    """Call the already-installed Agent Reach Exa connector without a shell."""
    expression = f"exa.web_search_exa(query: {json.dumps(query, ensure_ascii=False)}, numResults: {limit})"
    result = subprocess.run(
        [MCPORTER_PATH, "call", expression],
        capture_output=True,
        check=False,
        text=True,
        timeout=EXTERNAL_SEARCH_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Agent Reach Exa 当前不可用")
    return result.stdout


def _run_tavily_search(query: str, limit: int) -> dict[str, Any]:
    """Use Hermes' existing generic search only as a clearly labelled fallback."""
    command = (
        "import json,sys; from tools.web_tools import web_search_tool; "
        "payload=json.loads(sys.argv[1]); print(json.dumps(web_search_tool(payload['query'], limit=payload['limit'])))"
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = HERMES_AGENT_ROOT + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    result = subprocess.run(
        [HERMES_PYTHON_PATH, "-c", command, json.dumps({"query": query, "limit": limit}, ensure_ascii=False)],
        capture_output=True,
        check=False,
        text=True,
        timeout=EXTERNAL_SEARCH_TIMEOUT_SECONDS,
        env=environment,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Hermes Tavily 当前不可用")
    try:
        data: Any = json.loads(result.stdout)
        if isinstance(data, str):
            data = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Hermes Tavily 返回格式无效") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Hermes Tavily 返回格式无效")
    return data


def _parse_published_at(value: str) -> datetime | None:
    clean = (value or "").strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", clean)
        if not match:
            return None
        try:
            return datetime.fromisoformat(match.group(0))
        except ValueError:
            return None


def _source_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_excluded_news_result(title: str, url: str) -> bool:
    text = f"{title} {url}".lower()
    return any(marker in text for marker in ("polymarket", "kalshi", "odds", "prediction", "betting", "赔率", "预测"))


def _news_source_weight(url: str) -> int:
    host = _source_host(url)
    official_hosts = (
        "leagueoflegends.com", "lolesports.com", "lolesports.cn", "riotgames.com",
        "lck.co.kr", "lck.com", "lpl.qq.com",
    )
    reporting_hosts = (
        "invenglobal.com", "inven.co.kr", "bo3.gg", "sheepesports.com", "esports.gg", "dexerto.com",
    )
    if any(host == source or host.endswith(f".{source}") for source in official_hosts):
        return 2
    if any(host == source or host.endswith(f".{source}") for source in reporting_hosts):
        return 1
    return 0


def _parse_exa_news_results(raw: str, after: datetime, limit: int) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?ms)^Title:\s*(?P<title>.*?)\nURL:\s*(?P<url>.*?)\nPublished:\s*(?P<published>.*?)\nAuthor:\s*(?P<author>.*?)\nHighlights:\s*(?P<highlights>.*?)(?:\n---\s*|\Z)"
    )
    candidates: list[tuple[int, datetime, dict[str, Any]]] = []
    for match in pattern.finditer(raw):
        title = match.group("title").strip()
        url = match.group("url").strip()
        published_at = _parse_published_at(match.group("published"))
        if not title or not url or _is_excluded_news_result(title, url) or published_at is None:
            continue
        if published_at.date() < after.date():
            continue
        candidates.append((
            _news_source_weight(url),
            published_at,
            {
                "title": title,
                "url": url,
                "source": _source_host(url),
                "published_at": published_at.isoformat(),
                "highlights": match.group("highlights").strip()[:800],
                "freshness": "verified",
            },
        ))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in candidates[:limit]]


def _parse_tavily_news_results(raw: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    web = ((raw.get("data") or {}).get("web") or []) if isinstance(raw.get("data"), dict) else []
    if not isinstance(web, list):
        return []
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in web:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url or _is_excluded_news_result(title, url):
            continue
        candidates.append((
            _news_source_weight(url),
            {
                "title": title,
                "url": url,
                "source": _source_host(url),
                "published_at": "",
                "highlights": str(item.get("description") or item.get("content") or "").strip()[:800],
                "freshness": "unverified",
            },
        ))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in candidates[:limit]]


@mcp.tool(
    name="xiaoxue_search_external_news",
    annotations={"title": "搜索近期 LOL 外部资讯", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_search_external_news(query: str, recency_days: int = 14, limit: int = 5) -> str:
    """只读搜索近期 LOL 外部资讯：Exa 优先，过滤赔率/预测与窗口外结果；降级结果不宣称时效。"""

    clean_query = _clean_text(query, "资讯查询", min_length=2)
    days = _bounded_external_news_recency(recency_days)
    result_limit = _bounded_limit(limit, maximum=EXTERNAL_NEWS_MAX_RESULTS)
    after = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=days)
    search_query = _external_news_search_query(clean_query, after.date().isoformat())
    response: dict[str, Any] = {
        "query": clean_query,
        "search_query": search_query,
        "freshness": {"after": after.date().isoformat(), "rule": "只把带发布时间且在窗口内的 Exa 结果作为近期资讯。"},
    }

    try:
        exa_raw = await asyncio.to_thread(_run_exa_search, search_query, result_limit)
        exa_results = _parse_exa_news_results(exa_raw, after, result_limit)
        if exa_results:
            return _json({**response, "status": "ok", "provider": "agent-reach/exa", "results": exa_results})
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass

    try:
        tavily_raw = await asyncio.to_thread(_run_tavily_search, search_query, result_limit)
        tavily_results = _parse_tavily_news_results(tavily_raw, result_limit)
        if tavily_results:
            return _json({
                **response,
                "status": "fallback",
                "provider": "hermes/tavily",
                "results": tavily_results,
                "notice": "Exa 没有返回可核验的近期结果；以下仅是未验证时效的备选链接，不能据此断言“最新”。",
            })
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass

    return _json({
        **response,
        "status": "unavailable",
        "provider": "agent-reach/exa",
        "results": [],
        "notice": "暂未找到可核验的近期来源；没有用旧内容或赔率预测代替。",
    })


async def _api_request(
    method: Literal["GET", "POST", "PUT", "PATCH"],
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any] | list[Any]:
    if method not in {"GET", "POST", "PUT", "PATCH"} or not endpoint.startswith("/"):
        raise ValueError("不允许的产品 API 操作")

    allowed_exact = {
        "/daily-content",
        "/schedules",
        "/teams",
        "/fundamentals/teams",
        "/current-event/match-desk",
        "/current-event/collection",
        "/current-event/materials",
        "/trading-methods",
        "/current-event/judgment-context",
        "/current-event/judgment-discussion",
        "/current-event/scope-materials",
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
        "/scoregg/result",
        "/scoregg/results",
        "/champions/context",
        "/business-mutations/apply",
        "/data-refresh",

        "/current-event/match-workspace",
        "/current-event/match-workspace/changes",
        "/stage-review/candidates",
        "/trading-tk",
        "/tk/search",
        "/market-notes",
        "/team-trading-notes",
        "/research/match-brief",
    }
    allowed_patterns = (
        "/profile-full/[^/]+",
        r"/team-3d/[^/]+",
        r"/version-understanding/[^/]+",
        r"/team-trading-notes/[^/]+",
        r"/tk/entry/[^/]+",
        r"/current-event/match-run/facts/\d+",
        r"/current-event/collection/[a-f0-9]{24}",
        r"/current-event/collection/[a-f0-9]{24}/resume",
        r"/stage-review/candidates/\d+",
        r"/trading-tk/[^/]+\.md",
    )
    # Read-only discovery is intentionally open within Xiaoxue's local product
    # API.  The adapter still rejects every non-GET operation unless it is in
    # the explicit write contract below; this removes the artificial “forgot to
    # add one read endpoint” failure without opening writes or arbitrary hosts.
    if method != "GET":
        if method == "DELETE":
            raise ValueError("删除接口永不由小雪直接开放")
        _assert_safe_mutation(endpoint, payload)
    write_operations = {
        ("POST", "/team-trading-notes"),
        ("POST", "/business-mutations/apply"),
        ("PUT", "/current-event/match-workspace"),
        ("POST", "/current-event/match-workspace/changes"),
        ("POST", "/current-event/match-run/start"),
        ("POST", "/current-event/match-run/pause"),
        ("PUT", "/current-event/match-run/entry"),
        ("POST", "/current-event/match-run/candidates"),
        ("POST", "/current-event/match-run/advance"),
        ("PUT", "/current-event/match-run/judgment"),
        ("POST", "/trading-tk"),
        ("POST", "/current-event/collection"),
        ("POST", "/current-event/judgment-discussion"),
        ("POST", "/current-event/scope-materials"),
    }
    if method == "POST" and re.fullmatch(r"/current-event/collection/[a-f0-9]{24}/resume", endpoint):
        write_operations.add((method, endpoint))
    if method == "PUT" and re.fullmatch(r"/current-event/match-run/facts/\d+", endpoint):
        write_operations.add((method, endpoint))
    if method == "PUT" and re.fullmatch(r"/team-3d/[^/]+", endpoint):
        write_operations.add((method, endpoint))
    if method == "PATCH" and (
        re.fullmatch(r"/stage-review/candidates/\d+", endpoint)
        or re.fullmatch(r"/trading-tk/[^/]+\.md", endpoint)
    ):
        write_operations.add((method, endpoint))
    # Ordinary POST/PUT/PATCH operations are available to the product adapter;
    # irreversible operations were rejected above, before any network request.

    try:
        async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=timeout_seconds or REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.request(method, endpoint, params=params, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError("小雪工作台响应超时；操作结果尚不确定，请先读回原对象，不要重复提交。") from exc
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
        raise RuntimeError("小雪工作台连接中断；操作结果尚不确定，请先从原入口读回。") from exc


def _local_api_endpoint(endpoint: str) -> str:
    """Normalize product-relative and direct FastAPI paths.

    API_BASE_URL already ends in /api. Named tools use /health, while generic
    callers commonly paste /api/health; accept both without requesting
    /api/api/health.
    """
    clean_endpoint = _clean_text(endpoint, "接口路径")
    if not clean_endpoint.startswith("/") or ".." in clean_endpoint or "//" in clean_endpoint:
        raise ValueError("接口路径必须是小雪本地 API 的绝对路径")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", clean_endpoint):
        raise ValueError("接口路径格式无效")
    if clean_endpoint == "/api":
        return "/"
    return clean_endpoint[4:] if clean_endpoint.startswith("/api/") else clean_endpoint


@mcp.tool(
    name="xiaoxue_query_readonly_api",
    annotations={"title": "查询小雪只读数据接口", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_query_readonly_api(endpoint: str, params: dict[str, Any] | None = None) -> str:
    """查询本地只读接口；接受 `/health` 和直连形式 `/api/health`。"""
    clean_endpoint = _local_api_endpoint(endpoint)
    clean_params = params if isinstance(params, dict) else {}
    data = await _api_request("GET", clean_endpoint, params=clean_params)
    return _json(_read_result(
        data, capability="readonly_api", version="1.0.0", summary="已读取小雪只读数据接口", source=clean_endpoint,
    ))


@mcp.tool(
    name="xiaoxue_mutate_safe_api",
    annotations={"title": "执行小雪普通业务更新", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_mutate_safe_api(method: Literal["POST", "PUT", "PATCH"], endpoint: str, payload: dict[str, Any] | None = None) -> str:
    """执行普通产品更新；接受 `/path` 和 `/api/path`，高风险动作仍由能力层拒绝。"""
    clean_endpoint = _local_api_endpoint(endpoint)
    return _json(await _api_request(method, clean_endpoint, payload=payload if isinstance(payload, dict) else {}))


@mcp.tool(
    name="xiaoxue_refresh_results_and_ts",
    annotations={"title": "刷新赛果和 TS 表", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_refresh_results_and_ts() -> str:
    """刷新 ScoreGG 赛果并重算 TS；失败时保留具体阶段并交给小白排查。"""
    data = await _api_request("POST", "/data-refresh", payload={}, timeout_seconds=900.0)
    return _json(_read_result(
        data, capability="data_refresh", version="1.0.0", summary="已刷新赛果和 TS", source="/data-refresh",
    ))


@mcp.tool(
    name="xiaoxue_get_today",
    annotations={"title": "读取小雪今日入口", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_today(date: str = "today", offset: int = 0) -> str:
    """读取日报成品链接、冻结时点、赛程与最新材料摘要；next_offset继续，单场正文由比赛成果工具读取。"""

    clean_date = (date or "today").strip() or "today"
    data = await _api_request("GET", "/daily-content", params={"date": clean_date})
    report = data.get("report") or {}
    matches, materials = data.get("matches") or [], data.get("latest_matches") or []
    start = max(0, int(offset))
    output = {"date": data.get("date"), "day_state": data.get("day_state"),
              "report": {key: report.get(key) for key in ("publication_status", "published", "snapshot_at", "snapshot_at_basis", "url")},
              "operating_state": (data.get("operating_state") or {}).get("state"),
              "matches_total": len(matches), "materials_total": len(materials),
              "read_hint": "日报URL是固定截面的成品；最新消息按task_id读取比赛成果，next_offset继续赛程与材料目录。"}
    # Same offset pages the two compact directories without exposing local files.
    page_size = 4
    while True:
        output["matches"] = [{key: str(row.get(key) or "")[:120 if key == "stage" else 40] for key in ("team_a", "team_b", "date", "time", "stage", "format")} for row in matches[start:start + page_size]]
        output["latest_matches"] = [{"task_id": row.get("task_id"), "state": row.get("state"), "updated_at": row.get("updated_at"), "summary": str(row.get("summary") or "")[:180]} for row in materials[start:start + page_size]]
        output["next_offset"] = start + page_size if max(len(matches), len(materials)) > start + page_size else None
        if len(_json(output)) <= 3000 or page_size == 1:
            return _json(output)
        page_size -= 1

@mcp.tool(
    name="xiaoxue_get_change_basket",
    annotations={"title": "读取小雪待修改", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_change_basket(limit: int = 12, include_paused: bool = True) -> str:
    """读取钧钧当前想聊的待修改及模块快照；用于“聊聊待修改”。

    只返回对话需要的模块名称、感受、当前焦点和人话快照，不要求钧钧提供模块编号，
    也不返回项目中心的内部实现信息。
    """

    data = await _api_request(
        "GET",
        "/project-center/change-basket",
        params={"status": "active" if include_paused else "pending", "limit": _bounded_limit(limit, maximum=20)},
    )
    payload = data if isinstance(data, dict) else {}
    basket = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items = basket.get("items") if isinstance(basket.get("items"), list) else []
    visible = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        snapshot = item.get("context_snapshot") if isinstance(item.get("context_snapshot"), dict) else {}
        visible.append({
            "module": str(item.get("module_name") or snapshot.get("module_name") or "还没归类的想法"),
            "note": str(item.get("optional_note") or ""),
            "state": "暂放" if item.get("status") == "paused" else "待聊",
            "is_focus": bool(item.get("is_focus")),
            "what_it_helps": str(snapshot.get("purpose") or ""),
            "current_state": str((snapshot.get("runtime") or {}).get("label") or "待在对话里确认"),
        })
    focus = next((item for item in visible if item["is_focus"]), None)
    return _json({
        "status": "empty" if not visible else "ok",
        "summary": "待修改框还没有内容" if not visible else f"已读到 {len(visible)} 条待修改，先从当前焦点开始聊即可",
        "current_focus": focus,
        "items": visible,
        "next_step": "先说明这些感觉的关联与影响，再和钧钧自然讨论；不要把它们当成已承诺施工的工单。",
    })


@mcp.tool(
    name="xiaoxue_find_schedules",
    annotations={"title": "查询小雪赛程", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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
    data = await _api_request("GET", "/schedules", params=params)
    return _json(_read_result(
        data,
        capability="team_data",
        version="1.0.0",
        summary="已读取正式赛程",
        source="/schedules",
    ))


def _material_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if re.search(r"/home/|/tmp/|file://|Traceback|SKILL\.md", value, re.I):
        return ""
    if value.lstrip().startswith(("{", "[")):
        try:
            if isinstance(json.loads(value), (dict, list)):
                return ""
        except ValueError:
            pass
    return value


def _material_source(item: dict) -> dict:
    """A readable citation is not the private/raw input audit bundle."""
    result = {key: text for key in (
        "text", "title", "source_title", "source", "published_at", "updated_at", "verification", "conditions", "counterevidence",
        "why_relevant", "kind", "source_kind", "applicability", "evidence_quote", "basis_note",
    ) if (text := _material_text(item.get(key)))}
    url = _material_text(item.get("url"))
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
        result["url"] = url
    if result.get("url") or item.get("kind") in {"author_analysis", "reported_information", "official_background"}:
        result["published_at"] = _material_text(item.get("published_at"))
        if not result["published_at"]:
            result["date_note"] = "发布日期未知"
    return result


def _material_item(item: dict, *, personal_analysis: bool = False) -> dict:
    result = _material_source(item)
    if personal_analysis:
        for key in ("text", "conditions", "counterevidence", "why_relevant"):
            if key in result:
                # Input-row references remain in the audit data; readable evidence stays separate.
                result[key] = re.sub(r"(?<![A-Za-z0-9])[IPM]\d+(?:\s*(?:[、,，/]|与|和|及)\s*[IPM]\d+)*(?![A-Za-z0-9])", "", result[key])
                result[key] = re.sub(r"[（(]\s*[）)]", "", result[key])
    evidence = [_material_source(row) for row in item.get("evidence", []) if isinstance(row, dict) and _material_text(row.get("text"))]
    if evidence:
        result["evidence"] = evidence
    return result


def _revision_change(data: dict, expected_revision: str) -> dict | None:
    """A live reread may change; never append a new revision to older pages."""
    if len(expected_revision) > 128:
        raise ValueError("expected_revision过长")
    if expected_revision and expected_revision != data.get("revision", ""):
        output = {key: data[key] for key in ("task_id", "method_id", "match", "subject", "revision") if key in data}
        output.update(revision_changed=True, expected_revision=expected_revision, restart_offset=0, text="", next_offset=None,
                      read_hint="成果已更新，丢弃此前分页；沿用原对象和栏目，以新revision作为expected_revision从offset=0重读，不拼接两版。")
        if len(_json(output)) > 3000:
            raise ValueError("分页元信息超过读取预算")
        return output
    return None


def _text_page(data: dict, text: str, offset: int = 0) -> dict:
    """Shared escaped-JSON budget for material, judgment and cached reply pages."""
    offset = max(0, int(offset))
    output = {**data, "offset": offset, "total_chars": len(text), "text": "", "next_offset": None}
    if len(_json(output)) > 3000:
        raise ValueError("分页元信息超过读取预算")
    low, high = 0, min(1400, max(0, len(text) - offset))
    while low < high:
        length = (low + high + 1) // 2
        output.update(text=text[offset:offset + length], next_offset=offset + length if offset + length < len(text) else None)
        if len(_json(output)) <= 3000:
            low = length
        else:
            high = length - 1
    if not low and offset < len(text):
        raise ValueError("分页元信息未留下正文读取空间")
    output.update(text=text[offset:offset + low], next_offset=offset + low if offset + low < len(text) else None)
    return output


def _material_summary(payload: dict, *, section: str = "", offset: int = 0, expected_revision: str = "") -> dict:
    task = payload.get("task") or {}
    result = payload.get("result") or {}
    match = result.get("match") or task.get("match") or {}
    output = {"task_id": str(task.get("id") or "")[:24], "state": str(task.get("state") or "")[:20],
              "message": _material_text(task.get("message"))[:100],
              "match": {key: _material_text(match.get(key))[:limit] for key, limit in (("team_a", 40), ("team_b", 40), ("event", 120), ("match_date", 10), ("match_time", 20))},
              "updated_at": str(result.get("updated_at") or "")[:40], "revision": str(result.get("revision") or "")[:128]}
    subject = result.get("subject") or task.get("subject") or {}
    if subject:
        output["subject"] = {key: _material_text(subject.get(key))[:limit] for key, limit in (("scope", 10), ("event", 120), ("team", 40)) if subject.get(key)}
    if changed := _revision_change(output, expected_revision):
        return changed
    # Never return a whole evidence bundle to the model. All text remains pageable.
    sections = result.get("sections") or []
    offset = max(0, int(offset))
    if section:
        if section == "__limitations__":
            text = "\n".join(_material_text(item) for item in result.get("limitations", []))
        else:
            selected = next((item for item in sections if item["id"] == section), None)
            if not selected:
                raise ValueError("没有找到这部分比赛资料")
            text = "\n".join(_json(_material_item(item, personal_analysis=section == "analysis")) for item in selected.get("items", []))
        return _text_page({**output, "section": section[:100]}, text, offset)
    else:
        output.update(summary=_material_text(result.get("summary"))[:240],
                      limitations=[_material_text(item)[:90] for item in result.get("limitations", [])[:3]],
                      limitations_total=len(result.get("limitations", [])), limitations_section="__limitations__",
                      sections_total=len(sections), next_section_offset=offset + 6 if len(sections) > offset + 6 else None,
                      sections=[{"id": str(item["id"])[:80], "title": str(item.get("title", ""))[:40], "items": len(item.get("items") or [])} for item in sections[offset:offset + 6]],
                      read_hint="简单看看默认只转述takeaways和必要限制，不为补字数主动读version/news或铺目录。充分准备、对照或找反例时自主读相关section及后页的条件/反证，不让用户翻页；传首屏revision为expected_revision，revision_changed时丢弃旧页从0重读。限制用__limitations__。发布日期未知就明确未知，不从原文其他日期、导航或球员卡推断文章日期。")
        output["takeaways"] = []
        labels = {"ai_summary": "AI整理，请结合原文", "system_inference": "系统推导，未确认采用"}
        for name in ("digest", "shared_digest", "analysis", "comparison"):
            selected = next((item for item in sections if item.get("id") == name), None)
            if not selected or (name in {"digest", "shared_digest"} and selected.get("selection_status") != "screened"):
                continue
            first = next((item for item in selected.get("items", []) if _material_text(item.get("text"))), None)
            if first:
                readable = _material_item(first, personal_analysis=name == "analysis")
                output["takeaways"].append({"section": name, "text": _material_item(first, personal_analysis=name == "analysis").get("text", "")[:160],
                                            "basis": labels.get(first.get("verification"), "请结合来源核对"),
                                            **{key: readable[key][:140] for key in ("source", "conditions", "counterevidence") if readable.get(key)},
                                            **({"url": readable["url"]} if readable.get("url") and len(readable["url"]) <= 300 else {}),
                                            **({"published_at": _material_text(first.get("published_at"))[:40],
                                                "date_note": "" if _material_text(first.get("published_at")) else "发布日期未知"} if name in {"digest", "shared_digest"} else {}),
                                            "more": "按同名section读取完整正文与依据"})
        # Keep all lines represented while progressively shortening previews, not full pages.
        for limit in (120, 80, 40, 20):
            if len(_json(output)) <= 3000:
                break
            output["summary"] = output["summary"][:limit]
            output["limitations"] = [item[:limit] for item in output["limitations"]]
            for item in output["takeaways"]:
                for key in ("text", "source", "conditions", "counterevidence"):
                    if key in item:
                        item[key] = item[key][:limit]
        while len(_json(output)) > 3000 and output["sections"]:
            output["sections"].pop()
            output["next_section_offset"] = offset + len(output["sections"])
        if len(_json(output)) > 3000:
            for item in output["takeaways"]:
                item.pop("url", None)  # Full provenance is losslessly readable in the named section.
        if len(_json(output)) > 3000:
            raise ValueError("材料摘要超过读取预算，请按具体栏目读取")
    return output


@mcp.tool(name="xiaoxue_get_judgment_views", structured_output=False,
          annotations={"title": "查看可用判断角度", "readOnlyHint": True, "destructiveHint": False, "openWorldHint": False})
async def xiaoxue_get_judgment_views(offset: int = 0) -> str:
    """与工作台共用判断目录；选一个id后open读取对应已有内容，不要求用户记方法名称。"""
    data = await _api_request("GET", "/trading-methods")
    rows, offset = data.get("methods") or [], max(0, int(offset))
    views = [{"id": _material_text(row.get("id"))[:64], "title": _material_text(row.get("title"))[:60],
              "purpose": _material_text(row.get("purpose"))[:140], "status": str(row.get("status") or "")[:20],
              "primary": row.get("primary", True) is not False, "channel": str(row.get("channel") or "workbench")[:24]}
             for row in rows[offset:offset + 6]]
    output = {"views": views, "total": len(rows), "next_offset": offset + len(views) if offset + len(views) < len(rows) else None}
    while len(_json(output)) > 3000 and views:
        views.pop()
        output["next_offset"] = offset + len(views)
    return _json(output)


def _judgment_params(method_id: str, event: str = "", team: str = "", team_a: str = "", team_b: str = "",
                     match_date: str = "", match_time: str = "", match_format: str = "", as_of: str = "") -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", method_id):
        raise ValueError("判断入口不正确")
    values = {"method_id": method_id}
    for key, value in (("event", event), ("team", team), ("team_a", team_a), ("team_b", team_b),
                       ("match_date", match_date), ("match_time", match_time), ("match_format", match_format), ("as_of", as_of)):
        if value:
            values[key] = _clean_team(value) if key.startswith("team") else _clean_text(value, key)
    return values


@mcp.tool(name="xiaoxue_open_judgment", structured_output=False,
          annotations={"title": "打开判断所需的已有内容", "readOnlyHint": True, "destructiveHint": False, "openWorldHint": False})
async def xiaoxue_open_judgment(method_id: str, event: str = "", team: str = "", team_a: str = "", team_b: str = "",
                               match_date: str = "", match_time: str = "", match_format: str = "", as_of: str = "", offset: int = 0,
                               expected_revision: str = "") -> str:
    """只读实际正文与依据，不触发搜索、模型或保存。充分研究时自主按next_offset继续相关正文及依据，不让用户翻页。

    后页沿用相同对象/as_of，并将首屏revision作为expected_revision；revision_changed时丢弃旧页，从offset=0读新revision，不拼接两版。
    """
    data = await _api_request("GET", "/current-event/judgment-context", params=_judgment_params(method_id, event, team, team_a, team_b, match_date, match_time, match_format, as_of))
    metadata = {"method_id": method_id, "status": str(data.get("status") or "")[:30],
                "revision": str(data.get("revision") or "")[:128], "needed": data.get("needed") or [],
                "discussion_available": data.get("discussion_available") is True}
    if changed := _revision_change(metadata, expected_revision):
        return _json(changed)
    blocks = []
    for row in [*(data.get("contents") or []), *(data.get("analysis") or [])]:
        if not isinstance(row, dict):
            continue
        blocks.append("\n".join(filter(None, (_material_text(row.get("title")), _material_text(row.get("text")),
                                              _material_text(row.get("source_label")), _material_text(row.get("evidence_quote")),
                                              _material_item(row).get("url", "")))))
        for evidence in row.get("evidence", []):
            if isinstance(evidence, dict) and _material_text(evidence.get("text")):
                blocks.append("所用依据：" + _material_text(evidence["text"]) +
                              ("\n" + _material_item(evidence)["url"] if _material_item(evidence).get("url") else ""))
    blocks.extend(_material_text(value) for value in data.get("limitations", []))
    return _json(_text_page(metadata, "\n\n".join(blocks), offset))


# Short-lived unsaved replies only, so long answers remain fully readable without
# repeating a paid model request. Never a knowledge/user-record writer.
_JUDGMENT_REPLIES: OrderedDict = OrderedDict()


@mcp.tool(name="xiaoxue_discuss_judgment", structured_output=False,
          annotations={"title": "根据已有内容讨论判断", "readOnlyHint": False, "destructiveHint": False, "openWorldHint": False})
async def xiaoxue_discuss_judgment(method_id: str, question: str, event: str = "", team: str = "", team_a: str = "", team_b: str = "",
                                  match_date: str = "", match_time: str = "", match_format: str = "", history: list[dict] | None = None, as_of: str = "") -> str:
    """沿用open时的完整对象及as_of，明确提问后才调用现有模型；历史截止视图目前不重推。讨论未保存、未采用。长答复自主按reply_id及next_offset读完，不让用户说继续，不重复提问或调用模型。"""
    params = _judgment_params(method_id, event, team, team_a, team_b, match_date, match_time, match_format, as_of)
    question = _clean_text(question, "问题")
    if len(question) > 2000:
        raise ValueError("问题最多2000字")
    data = await _api_request("POST", "/current-event/judgment-discussion", payload={**params, "question": question, "history": history or []}, timeout_seconds=130.0)
    answer = _material_text(data.get("answer"))
    references = "\n".join(_material_text(row.get("title")) for row in data.get("references", []) if isinstance(row, dict))
    text = answer + ("\n\n依据：\n" + references if references else "")
    reply_id = secrets.token_hex(12)
    _JUDGMENT_REPLIES[reply_id] = (time.monotonic(), text)
    while len(_JUDGMENT_REPLIES) > 16:
        _JUDGMENT_REPLIES.popitem(last=False)
    output = _text_page({"reply_id": reply_id, "saved": False, "context_revision": str(data.get("context_revision") or "")[:128]}, text)
    return _json(output)


@mcp.tool(name="xiaoxue_get_judgment_reply", structured_output=False,
          annotations={"title": "继续读取本次未保存讨论", "readOnlyHint": True, "destructiveHint": False, "openWorldHint": False})
async def xiaoxue_get_judgment_reply(reply_id: str, offset: int = 0) -> str:
    """十分钟内自主按next_offset读完同一reply_id答复，不让用户翻页，不重复模型请求，不写知识。"""
    row = _JUDGMENT_REPLIES.get(reply_id)
    if not row or time.monotonic() - row[0] > 600:
        _JUDGMENT_REPLIES.pop(reply_id, None)
        raise ValueError("这次未保存讨论已过期，请在原会话继续")
    return _json(_text_page({"reply_id": reply_id, "saved": False}, row[1], offset))


@mcp.tool(name="xiaoxue_collect_match_materials", structured_output=False,
          annotations={"title": "自动准备比赛资料", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def xiaoxue_collect_match_materials(team_a: str, team_b: str, event: str = "", match_date: str = "today", match_time: str = "", match_format: str = "", refresh: bool = False) -> str:
    """研究比赛时自主收集并整理公开资料；无需用户贴来源。不改个人判断或长期知识。返回任务，未完成时用读回工具继续，不把处理中当完成。"""
    params = _match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format)
    payload = await _api_request("POST", "/current-event/collection", payload={**params, "refresh": bool(refresh)})
    return _json(_material_summary(payload))


@mcp.tool(name="xiaoxue_get_match_materials", structured_output=False,
          annotations={"title": "先看赛事/某队已整理的粗筛与系统解释", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def xiaoxue_get_match_materials(task_id: str = "", section: str = "", offset: int = 0,
                                    scope: str = "", event: str = "", team: str = "", expected_revision: str = "") -> str:
    """只读已整理成果：问S16赛事/某队有哪些现成内容时优先使用，默认先看粗筛+系统解释，不搜索、不调用模型、不保存。

    team='BLG'直接读当前赛事的BLG；scope='event'读当前赛事，event可指定正式全称如'S16 世界赛'，省略由当前赛事配置定位。
    task_id兼容原单场任务读回，与scope/event/team互斥。默认只转述takeaways和必要限制，不为补字数主动读version/news或铺目录。
    简单看看保持短摘要；充分准备、对照双方、找反例时自主用section和next_offset读相关正文、完整条件/反证，不让用户说继续或翻页，原文/旧版本/画像只按需分页。
    后页沿用相同对象与section，目录后页也传首屏revision为expected_revision；revision_changed时丢弃旧页，以新revision从offset=0重读，不拼接两版。
    published_at为空必须说明发布日期未知，不从原文其他日期、网页导航或球员卡猜文章日期；处理中不代表内容完成。
    """
    task_id, scope, event, team = (value.strip() for value in (task_id, scope, event, team))
    if task_id:
        if scope or event or team:
            raise ValueError("任务编号不能与赛事/队伍范围混用")
        if not re.fullmatch(r"[a-f0-9]{24}", task_id):
            raise ValueError("无效的比赛资料任务")
        payload = await _api_request("GET", f"/current-event/collection/{task_id}")
    else:
        scope = scope or ("team" if team else "event" if event else "")
        if scope not in {"event", "team"} or (scope == "event" and team) or (scope == "team" and not team):
            raise ValueError("请指定赛事或明确队伍，或使用原任务编号")
        params = {"scope": scope}
        if event:
            if len(event) > 200:
                raise ValueError("赛事名称过长")
            params["event"] = _clean_text(event, "赛事")
        if team:
            params["team"] = _clean_team(team)
        payload = await _api_request("GET", "/current-event/scope-materials", params=params)
    return _json(_material_summary(payload, section=section, offset=offset, expected_revision=expected_revision))


@mcp.tool(name="xiaoxue_get_upcoming_preparation", structured_output=False,
          annotations={"title": "查看近期比赛逐场准备进度", "readOnlyHint": True, "destructiveHint": False,
                       "idempotentHint": True, "openWorldHint": False})
async def xiaoxue_get_upcoming_preparation(offset: int = 0) -> str:
    """只读关注窗口逐场状态；有next_offset时自主读完，别让用户逐页催促。

    充分准备时，沿read_with读取相同修订的单场正文、条件和限制；列表不代替原文。
    """
    offset = max(0, min(int(offset), 200))
    batch = await _api_request("GET", "/current-event/preparation-coverage", params={"offset": offset, "limit": 4})
    items = []
    for row in batch.get("items") or []:
        match = row.get("match") or {}
        item = {"team_a": str(match.get("team_a") or "")[:40], "team_b": str(match.get("team_b") or "")[:40],
                "date": match.get("date"), "time": match.get("time"), "state": row.get("state"),
                "reason": str(row.get("reason") or "")[:120], "revision": row.get("revision")}
        if row.get("task_id") and row.get("state") in {"prepared", "partial"}:
            item["read_with"] = {"tool": "xiaoxue_get_match_materials", "task_id": row["task_id"],
                                 "expected_revision": row.get("revision") or ""}
        items.append(item)
    output = {"event": batch.get("event"), "window_start": batch.get("window_start"),
              "window_end": batch.get("window_end"), "confirmed_total": batch.get("confirmed_total"),
              "prepared": batch.get("prepared"), "partial": batch.get("partial"),
              "not_started": batch.get("not_started"), "pending_total": batch.get("pending_total"),
              "truncated": batch.get("truncated"), "items": items, "next_offset": batch.get("next_offset")}
    if len(_json(output)) > 3000:
        raise ValueError("比赛列表超过单次读取预算，请缩小单页内容")
    return _json(output)


@mcp.tool(
    name="xiaoxue_prepare_match",
    annotations={"title": "汇总单场交易底稿", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_prepare_match(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """只读单场事实及已有准备成果。充分准备时先沿prepared_materials.read_with读取本场正文、出处和条件，再按需补双方；不要把赛事task当成单场，也不要因正式赛程待定就忽略已有单场材料。不写交易或长期知识。"""

    params: dict[str, Any] = {"team_a": _clean_team(team_a), "team_b": _clean_team(team_b)}
    if event.strip():
        params["event"] = _clean_text(event, "赛事")
    if match_date.strip():
        params["match_date"] = _clean_text(match_date, "比赛日期")
    if match_time.strip():
        params["match_time"] = _clean_text(match_time, "比赛时间")
    if match_format.strip():
        params["match_format"] = _clean_text(match_format, "赛制")
    desk = await _api_request("GET", "/current-event/match-desk", params=params)
    prepared = _material_summary(desk.get("prepared_materials") or {})
    if prepared.get("task_id"):
        prepared["read_with"] = {"tool": "xiaoxue_get_match_materials", "task_id": prepared["task_id"],
                                 "expected_revision": prepared.get("revision", "")}
    quantitative = desk.get("quantitative") or {}
    fields = ("team", "region", "power_score", "volatility_score", "trend", "momentum", "status")
    output = {"match": desk.get("match") or {}, "quantitative": {
        "available": quantitative.get("available", False),
        **{side: {key: row[key] for key in fields if key in row}
           for side in ("team_a", "team_b") if isinstance(row := quantitative.get(side), dict)},
    }, "prepared_materials": prepared,
        "reading_note": "这是单场入口；已有成果按read_with继续读，不把赛事材料当成本场。队伍详细资料沿xiaoxue_get_team读取；统计差异不直接证明原因，旧背景不等于当前适用。"}
    if quantitative.get("reason"):
        output["quantitative"]["reason"] = _material_text(quantitative["reason"])[:200]
    comparison = quantitative.get("compare") or {}
    if "comparable" in comparison:
        output["quantitative"]["comparable"] = comparison["comparable"]
    if comparison.get("reason"):
        output["quantitative"]["comparison_note"] = _material_text(comparison["reason"])[:200]
    for limit in (100, 60, 30):
        if len(_json(output)) <= 3000:
            break
        prepared["summary"] = str(prepared.get("summary") or "")[:limit]
        for item in prepared.get("takeaways", []):
            for key in ("text", "source", "conditions", "counterevidence"):
                if key in item:
                    item[key] = item[key][:limit]
        prepared["sections"] = []
    if len(_json(output)) > 3000:
        output["prepared_materials"] = {key: prepared[key] for key in ("state", "task_id", "revision", "updated_at", "read_with") if key in prepared}
    if len(_json(output)) > 3000:
        raise ValueError("单场读取元信息超过预算，请按对象单独读取")
    return _json(output)


@mcp.tool(
    name="xiaoxue_get_gol_series_facts",
    annotations={"title": "查 Gol.gg 系列赛逐局事实", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_get_gol_series_facts(
    team_a: str, team_b: str, game_id: int, event: str = "", match_date: str = "today", match_time: str = "", match_format: str = "",
) -> str:
    """读取用户明确指定的 Gol.gg 对局页及同系列赛逐局 BP/时长/资源事实；不写入长期资料或覆盖 ScoreGG。"""
    return _json(await _api_request("GET", "/current-event/gol-series-evidence", params={
        **_match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "game_id": _positive_id(game_id, "Gol.gg 对局编号"),
    }))


@mcp.tool(
    name="xiaoxue_get_gol_tournament_facts",
    annotations={"title": "查 Gol.gg 赛事事实", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_get_gol_tournament_facts(tournament: str) -> str:
    """读取指定 Gol.gg 赛事页的赛制、局数、平均时长与可定位对局；不做跨赛事结论。"""
    return _json(await _api_request("GET", "/gol/tournament", params={"tournament": _clean_text(tournament, "赛事")}))


@mcp.tool(
    name="xiaoxue_find_gol_entities",
    annotations={"title": "定位 Gol.gg 赛事对象", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_find_gol_entities(tournament: str, kind: str = "all", query: str = "", limit: int = 20) -> str:
    """在指定赛事页定位 Gol.gg 队伍或选手编号；没有唯一命中时返回候选，不猜测。"""
    return _json(await _api_request("GET", "/gol/entities", params={"tournament": _clean_text(tournament, "赛事"), "kind": _clean_text(kind, "对象类型"), "query": (query or "").strip(), "limit": _bounded_limit(limit, maximum=50)}))


@mcp.tool(
    name="xiaoxue_get_gol_team_facts",
    annotations={"title": "查 Gol.gg 队伍赛事事实", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_get_gol_team_facts(team_id: int, tournament: str) -> str:
    """读取指定 Gol.gg 队伍在赛事内的基础事实；不自动写入队伍画像。"""
    return _json(await _api_request("GET", "/gol/team", params={"team_id": _positive_id(team_id, "Gol.gg 队伍编号"), "tournament": _clean_text(tournament, "赛事")}))


@mcp.tool(
    name="xiaoxue_get_gol_tournament_bp",
    annotations={"title": "查 Gol.gg 赛事 BP 事实", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_get_gol_tournament_bp(tournament: str) -> str:
    """读取指定赛事页面的英雄禁用与分位置选用次数；只返回事实，不自动下优先级结论。"""
    return _json(await _api_request("POST", "/gol/query", payload={"kind": "bp", "tournament": _clean_text(tournament, "赛事")}))


@mcp.tool(
    name="xiaoxue_get_gol_player_facts",
    annotations={"title": "查 Gol.gg 选手赛事事实", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    structured_output=False,
)
async def xiaoxue_get_gol_player_facts(player_id: int, tournament: str) -> str:
    """读取指定 Gol.gg 选手在赛事内的基础事实；不自动写入选手画像。"""
    return _json(await _api_request("GET", "/gol/player", params={"player_id": _positive_id(player_id, "Gol.gg 选手编号"), "tournament": _clean_text(tournament, "赛事")}))



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
    structured_output=False,
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
    """打开、切换或恢复单场，并在首轮同包返回完整资料分区所需的聚合数据。"""

    resolved_date = _resolve_command_match_date(user_command, match_date)
    payload = {**_match_payload(team_a, team_b, event=event, match_date=resolved_date, match_time=match_time, match_format=match_format),
               "mode": _clean_text(mode, "运行模式")}
    if focus.strip():
        payload["focus"] = _clean_text(focus, "当前模块")
    result = await _api_request("POST", "/current-event/match-run/start", payload=payload)
    summary = _first_turn_run_summary(result)
    try:
        brief = await _api_request("GET", "/research/match-brief", params={
            **_match_params(
                team_a,
                team_b,
                event=event,
                match_date=resolved_date,
                match_time=match_time,
                match_format=match_format,
            ),
            "game": "lol",
        })
    except Exception:
        brief = {
            "status": "unavailable",
            "boundary": "单场资料聚合暂不可用；仍可使用已打开的临时比赛线程，不得改走通用工具查库。",
        }
    if isinstance(summary, dict):
        summary["first_turn_brief"] = _slim_first_turn_brief(
            brief, drop_guide=bool(summary.get("guide")),
        )
    return _json(summary)


@mcp.tool(
    name="xiaoxue_get_match_run",
    annotations={"title": "读取一场临时交易推演", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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
    structured_output=False,
)
async def xiaoxue_get_active_match_trade() -> str:
    """用户说继续但没有重复队名时，读取当前正在讨论的单场交易推演。"""

    return _json(await _api_request("GET", "/current-event/match-run/active"))


@mcp.tool(
    name="xiaoxue_pause_match_trade",
    annotations={"title": "暂存并放下当前比赛", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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

    _clean_text(user_command, "用户原始指令")
    return _json(await _api_request("POST", "/current-event/match-run/pause", payload=_match_payload(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_save_match_trade_entry",
    annotations={"title": "更新单场交易推演的一项", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "section": section,
        "content": _clean_text(content, "当前交易判断"),

    }
    result = await _api_request("PUT", "/current-event/match-run/entry", payload=payload)
    return _json(_save_entry_ack(result, section=section))


@mcp.tool(
    name="xiaoxue_update_match_run_fact",
    annotations={"title": "修正一条比赛依据", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
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
    structured_output=False,
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
    """更新当前临时比赛上下文的阶段；不影响赛果读取或长期知识。"""

    _clean_text(user_command, "用户原始指令")
    payload = {**_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
               "phase": _clean_text(phase, "流程阶段")}
    return _json(await _api_request("POST", "/current-event/match-run/advance", payload=payload))


@mcp.tool(
    name="xiaoxue_save_virtual_judgment",
    annotations={"title": "留存赛前虚拟判断", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
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

    _clean_text(user_command, "用户原始指令")
    payload = {
        **_match_payload(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format),
        "direction": _clean_text(direction, "方向"), "reasons": _clean_text(reasons, "理由"),
        "handling": _clean_text(handling, "处理"), "change_conditions": _clean_text(change_conditions, "变化条件"),
    }
    return _json(await _api_request("PUT", "/current-event/match-run/judgment", payload=payload))


@mcp.tool(
    name="xiaoxue_get_score_evidence",
    annotations={"title": "读取 ScoreGG 比赛证据", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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
    """读取本地 ScoreGG 导入证据；完全独立于交易推演和状态机。"""

    params = _match_params(team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format)
    params["view"] = _clean_text(view, "查看阶段")
    return _json(await _api_request("GET", "/current-event/score-evidence", params=params))


@mcp.tool(
    name="xiaoxue_get_champion_context",
    annotations={"title": "读取英雄版本资料", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_champion_context(champion: str, version: str = "") -> str:
    """读取 Data Dragon 英雄静态资料；适合核对技能、标签与版本属性，不给职业胜率。"""
    return _json(await _api_request("GET", "/champions/context", params={
        "champion": _clean_text(champion, "英雄"), "version": (version or "").strip(),
    }))


@mcp.tool(
    name="xiaoxue_get_score_result",
    annotations={"title": "查询 ScoreGG 已完赛赛果", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_score_result(
    team_a: str,
    team_b: str,
    event: str = "",
    match_date: str = "",
    match_time: str = "",
    match_format: str = "",
) -> str:
    """查询一场已导入的 ScoreGG 赛果；纯只读，不触碰交易推演。"""

    return _json(await _api_request("GET", "/scoregg/result", params=_match_params(
        team_a, team_b, event=event, match_date=match_date, match_time=match_time, match_format=match_format,
    )))


@mcp.tool(
    name="xiaoxue_find_score_results",
    annotations={"title": "收集 ScoreGG 已完赛赛果", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_find_score_results(team: str = "", date_from: str = "", date_to: str = "", limit: int = 20) -> str:
    """按可选队伍与日期窗口收集已导入赛果；适合“昨天/近几天赛果”等泛查询。"""
    params: dict[str, Any] = {"limit": _bounded_limit(limit)}
    if team.strip():
        params["team"] = _clean_team(team)
    if date_from.strip():
        params["date_from"] = date_from.strip()
    if date_to.strip():
        params["date_to"] = date_to.strip()
    data = await _api_request("GET", "/scoregg/results", params=params)
    return _json(_read_result(
        data, capability="current_event", version="1.0.0", summary="已收集 ScoreGG 已完赛赛果", source="/scoregg/results",
    ))


@mcp.tool(
    name="xiaoxue_get_match_run_review",
    annotations={"title": "读取单场赛后复盘底稿", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
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
    """Return a bounded first-turn envelope and hide internal fact identifiers."""
    if not isinstance(result, dict):
        return result
    # Never mutate the API response in place. Test doubles and some clients may
    # reuse the same mapping for the follow-up brief request; attaching that
    # mapping to itself would create a circular, non-serializable response.
    result = dict(result)
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
            "boundary": "只作本场提醒；小雪结合当前证据自行判断是否采用。",
        },
        "reply_contract": {
            "start": f"当前：{match.get('team_a', '')} vs {match.get('team_b', '')}｜正在看：{focus_label}",
            "shape": "结论地图 + 完整分区",
            "rules": [
                "本工具的 first_turn_brief 已聚合双方、长期知识/TK、资料档案、市场记录、冲突和缺口，首轮直接完整展示",
                "通常优先使用已聚合信息；只有缺口会改变结论时再补读其他资料",
                "不强推固定分析顺序，允许根据当前证据自行取舍",
                "明确要求最新、近期、外部或实时资料时直接联网搜索",
                "不先发简短预告，不等待继续，不要求固定口令",
            ],
        },
    }
    if result.get("mode") == "virtual_pre":
        summary["debug_replay"] = True
    return summary


@mcp.tool(
    name="xiaoxue_remember",
    annotations={"title": "写入钧钧明确指定的 TK", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_remember(text: str, trading: bool = False) -> str:
    """仅当钧钧明确提到 TK 或要求写进 TK 时写入；交易 TK 使用独立类型和复查状态。"""

    content = _clean_text(text, "记录内容", min_length=2)
    if trading:
        return _json(await _api_request("POST", "/trading-tk", payload={
            "statement": content, "source_command": "xiaoxue_remember(trading=true)",
            "category": "general", "scope": "global",
        }))
    return _json(await _api_request("POST", "/tk/remember", payload={"text": content, "tags": []}))


@mcp.tool(
    name="xiaoxue_search_trading_tk",
    annotations={"title": "搜索通用交易 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_search_trading_tk(
    query: str = "",
    scope: Literal["global", "region", "team", "player", "all"] = "all",
    region: str = "",
    subject: str = "",
    version_context: str = "",
    limit: int = 30,
) -> str:
    """从统一 TK 资料库找回带交易标签的笔记。"""

    return _json(await _api_request("GET", "/trading-tk", params={
        "q": (query or "").strip(), "status": "all", "scope": scope,
        "region": (region or "").strip(), "subject": (subject or "").strip(),
        "version_context": (version_context or "").strip(), "limit": _bounded_limit(limit, maximum=100),
    }))


@mcp.tool(
    name="xiaoxue_add_stage_candidate",
    annotations={"title": "把新认识放入阶段整理", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
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
    structured_output=False,
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
    structured_output=False,
)
async def xiaoxue_update_stage_candidate(user_command: str, candidate_id: int, status: Literal["ignored", "applied"]) -> str:
    """用户决定本轮不处理，或长期正源已确认写回并读回后，更新候选状态。"""

    _clean_text(user_command, "用户原始指令")
    return _json(await _api_request("PATCH", f"/stage-review/candidates/{int(candidate_id)}", payload={"status": status}))


@mcp.tool(
    name="xiaoxue_get_team",
    annotations={"title": "读取小雪队伍资料", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_team(team: str, trading_note_limit: int = 8) -> str:
    """一次读取队伍画像、TS、交易备注和当前已整理队伍材料，先复用再补缺。

    prepared_materials是当前赛事该队的已有研究，不是旧画像；充分准备/比较双方时沿read_with读取相关栏目及条件、反证，再补查缺失。
    旧画像、作者观点、系统推导保持原身份；比分或终局统计不证明输赢原因，没有过程证据的解释标为待证假设。
    """

    clean_team = _clean_team(team)
    encoded = quote(clean_team, safe="")
    responses = await asyncio.gather(
        _api_request("GET", f"/profile-full/{encoded}"),
        _api_request("GET", f"/version-understanding/{encoded}"),
        _api_request(
            "GET",
            f"/team-trading-notes/{encoded}",
            params={"status": "active", "limit": _bounded_limit(trading_note_limit, maximum=20)},
        ),
        _api_request(
            "GET",
            "/fundamentals/teams",
            params={"scope": "all", "team": clean_team, "limit": 1},
        ),
        _api_request("GET", "/current-event/scope-materials", params={"scope": "team", "team": clean_team}),
        return_exceptions=True,
    )
    for response in responses[:4]:
        if isinstance(response, Exception):
            raise response
    profile, version, notes, fundamentals, materials = responses
    if isinstance(materials, Exception):
        prepared_reading = {"state": "unavailable", "message": "已整理队伍材料读取失败，不代表没有材料；其余资料可继续使用。"}
    else:
        summary = _material_summary(materials)
        prepared_reading = {key: summary[key] for key in ("state", "revision", "updated_at", "takeaways", "limitations", "sections") if key in summary}
        prepared_reading["read_with"] = {"tool": "xiaoxue_get_match_materials", "team": clean_team, "expected_revision": summary.get("revision", "")}
    ts = next((item for item in fundamentals.get("teams", []) if item.get("short_name", "").upper() == clean_team.upper()), None)

    # 精简：只保留模型要读的字段，去掉 _read_result 审计壳和长摘要
    profile_text = ""
    if isinstance(profile, dict) and profile.get("markdown"):
        profile_text = str(profile.get("markdown", "")).strip()
    ts_display = (ts or {}).get("ts_display") or {}
    trading_titles = []
    if isinstance(notes, dict):
        for note in notes.get("notes", []) or []:
            title = note.get("title") or note.get("concept") or note.get("filename") or ""
            if title:
                trading_titles.append(str(title).strip())
    knowledge_titles = []
    if isinstance(version, dict):
        for item in version.get("tk_items", []) or []:
            title = item.get("title") or ""
            if title:
                knowledge_titles.append(str(title).strip())

    slim = {
        "team": clean_team,
        "region": (ts or {}).get("region", ""),
        "profile": profile_text,
        "ts": {
            "power_score": ts_display.get("power_score"),
            "volatility_score": ts_display.get("volatility_score"),
            "trend": ts_display.get("trend"),
            "momentum": ts_display.get("momentum"),
            "status": ts_display.get("status"),
        },
        "trading_notes": trading_titles,
        "related_knowledge": knowledge_titles,
        "prepared_materials": prepared_reading,
        "reading_note": "先复用已整理材料及其出处、条件和反证。旧画像须核对本届适用性；统计现象不等于归因，无过程证据时只作待证假设；不同赛区TS分数不直接比较。",
        "profile_truncated": False,
    }
    # The model-facing contract is deliberately smaller than the audit/API
    # envelope. Do not leak raw mu/sigma/ts or long TK bodies into context.
    encoded_slim = _json(slim)
    while len(encoded_slim) > 3000 and (slim["trading_notes"] or slim["related_knowledge"]):
        if len(slim["trading_notes"]) >= len(slim["related_knowledge"]):
            slim["trading_notes"].pop()
        else:
            slim["related_knowledge"].pop()
        encoded_slim = _json(slim)
    while len(encoded_slim) > 3000 and len(slim["profile"]) > 80:
        slim["profile"] = slim["profile"][:max(80, len(slim["profile"]) // 2)]
        slim["profile_truncated"] = True
        encoded_slim = _json(slim)
    if len(encoded_slim) > 3000:
        # Keep the direct reading identity, not a misleading slice of evidence.
        slim["prepared_materials"] = {key: prepared_reading[key] for key in ("state", "revision", "updated_at", "read_with", "message") if key in prepared_reading}
        slim["prepared_materials"]["message"] = "已有材料须按read_with读取，摘要未在此展开。" if not isinstance(materials, Exception) else prepared_reading["message"]
        encoded_slim = _json(slim)
    return encoded_slim


@mcp.tool(
    name="xiaoxue_get_ts_updates",
    annotations={"title": "读取队伍 TS 更新记录", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_ts_updates(team: str, limit: int = 20, days: int = 30) -> str:
    """读取某队最近 TS 字段变化，供回答“何时更新、更新了什么”。"""

    clean_team = _clean_team(team)
    data = await _api_request(
        "GET",
        f"/ts-updates/{quote(clean_team, safe='')}",
        params={"limit": _bounded_limit(limit), "days": _bounded_days(days)},
    )
    return _json(_read_result(
        data,
        capability="ts_update_history",
        version="1.0.0",
        summary="已读取队伍 TS 更新记录",
        source=f"/ts-updates/{quote(clean_team, safe='')}",
    ))


@mcp.tool(
    name="xiaoxue_update_team_profile",
    annotations={"title": "更新队伍画像", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_update_team_profile(
    user_command: str,
    team: str,
    positioning: str = "",
    win_path: str = "",
    lose_path: str = "",
    key_points: str = "",
    bp_tendency: str = "",
) -> str:
    """更新一支队伍的统一画像。队伍画像固定为：队伍定位、怎么赢、怎么输、关键点、BP 倾向；用户说改哪一项就只传对应字段，后端自动保留其余项并读回。不得用这个工具维护首发、TK、TS 或旧三维。"""
    _clean_text(user_command, "用户原始指令")
    clean_team = _clean_team(team)
    changes = {
        key: value.strip() for key, value in {
            "positioning": positioning, "win_path": win_path, "lose_path": lose_path,
            "key_points": key_points, "bp_tendency": bp_tendency,
        }.items() if value and value.strip()
    }
    if not changes:
        raise ValueError("至少提供一项要更新的队伍画像内容")
    return _json(await _api_request("PUT", f"/team-profile/{quote(clean_team)}", payload=changes))


@mcp.tool(
    name="xiaoxue_apply_business_mutation",
    annotations={"title": "执行小范围业务更新", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_apply_business_mutation(user_command: str, target_type: str, target: str, changes: dict, reason: str = "") -> str:
    """按统一业务变更合同处理已有正源的小范围更新；首发支持完整五人名单或单人/局部更新，结构级风险由后端升级干预。"""
    _clean_text(user_command, "用户原始指令")
    return _json(await _api_request("POST", "/business-mutations/apply", payload={
        "target_type": _clean_text(target_type, "变更对象类型"),
        "target": _clean_text(target, "变更对象"),
        "changes": changes or {},
        "reason": (reason or "").strip(),
    }))


@mcp.tool(
    name="xiaoxue_search_tk",
    annotations={"title": "搜索小雪 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_search_tk(query: str, team: str = "", limit: int = 10) -> str:
    """通过工作台正式 TK 搜索入口检索，不扫描文件系统。"""

    params: dict[str, Any] = {"q": _clean_text(query, "查询词"), "limit": _bounded_limit(limit, maximum=20)}
    if team.strip():
        params["team"] = _clean_team(team)
    data = await _api_request("GET", "/tk/search", params=params)
    return _json(_read_result(
        _slim_tk_search(data),
        capability="tk_knowledge",
        version="1.0.0",
        summary="已搜索 TK 正式入口",
        source="/tk/search",
    ))


@mcp.tool(
    name="xiaoxue_get_tk_entry",
    annotations={"title": "读取一条小雪 TK", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_get_tk_entry(filename: str) -> str:
    """读取 TK 搜索结果中的一条正式正文。"""

    clean = _clean_text(filename, "TK 文件名")
    if "/" in clean or "\\" in clean or clean in {".", ".."}:
        raise ValueError("TK 文件名无效")
    return _json(await _api_request("GET", f"/tk/entry/{quote(clean, safe='')}"))


TK_ADAPTER_BASE_URL = os.getenv("XIAOXUE_TK_ADAPTER_BASE_URL", get_service_url("mempalace_tk_url"))


@mcp.tool(
    name="xiaoxue_delete_tk",
    annotations={"title": "删除一条小雪 TK", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_delete_tk(filename: str) -> str:
    """用户明确要求删除某条 TK 时，把正源移入归档并清掉 MemPalace 向量；不做物理删除，可回退。"""

    clean = _clean_text(filename, "TK 文件名")
    if "/" in clean or "\\" in clean or clean in {".", ".."}:
        raise ValueError("TK 文件名无效")
    try:
        async with httpx.AsyncClient(base_url=TK_ADAPTER_BASE_URL, timeout=60.0) as client:
            response = await client.post("/api/delete", json={"filename": clean})
            response.raise_for_status()
            return _json(response.json())
    except httpx.TimeoutException as exc:
        raise RuntimeError("TK 删除适配器响应超时；本次没有写入") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"TK 删除被拒（{exc.response.status_code}）") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("TK 删除适配器当前不可用；本次没有写入") from exc


@mcp.tool(
    name="xiaoxue_list_market_notes",
    annotations={"title": "读取交易 TK 中的盘口判断（兼容）", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    structured_output=False,
)
async def xiaoxue_list_market_notes(limit: int = 10) -> str:
    """兼容读取交易 TK 中 category=market 的盘口判断；不读取盘口记录表。"""

    return _json(await _api_request("GET", "/market-notes", params={"game": "lol", "limit": _bounded_limit(limit, maximum=30)}))


PUBLIC_TOOL_FUNCTIONS = tuple(tool.name for tool in mcp._tool_manager.list_tools())


if __name__ == "__main__":
    mcp.run()
