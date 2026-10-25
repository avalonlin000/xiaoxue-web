#!/usr/bin/env python3
"""Thin adapter for Xiaoxue's local zero-key web-search service.

The backend is an already-running SearXNG-compatible endpoint installed on the
same host.  This module only normalizes its result shape for project consumers;
it does not implement a search engine or depend on paid API keys.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

LIBS_DIR = Path("/home/ubuntu/lol_data/libs")
MAX_RESULTS = 50
MAX_SNIPPET_CHARS = 1600
DEFAULT_TIMEOUT_SECONDS = 20.0


def _system_service_url(name: str) -> str:
    """Read the single project service registry instead of hard-coding URLs."""
    if str(LIBS_DIR) not in sys.path:
        sys.path.insert(0, str(LIBS_DIR))
    try:
        from config import get_service_url  # type: ignore

        return str(get_service_url(name) or "").strip()
    except Exception:
        return ""


def search_service_url() -> str:
    value = os.getenv("XIAOXUE_SEARCH_URL", "").strip() or _system_service_url("web_search_url")
    if not value:
        raise RuntimeError("本地免费搜索服务未配置（services.web_search_url）")
    return value


def search_service_health_url() -> str:
    value = os.getenv("XIAOXUE_SEARCH_HEALTH_URL", "").strip() or _system_service_url("web_search_health")
    if not value:
        raise RuntimeError("本地免费搜索服务健康地址未配置（services.web_search_health）")
    return value


def _clean_text(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _safe_http_url(value: Any) -> str:
    url = str(value or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _with_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(params.items())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params,
                       urlencode(query, doseq=True), parsed.fragment))


def _result_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results")
    if rows is None:
        rows = payload.get("web")
    if rows is None and isinstance(payload.get("data"), dict):
        rows = payload["data"].get("web") or payload["data"].get("results")
    return [item for item in rows or [] if isinstance(item, dict)]


def _normalize_result(item: dict[str, Any]) -> dict[str, Any] | None:
    url = _safe_http_url(item.get("url") or item.get("link"))
    title = _clean_text(item.get("title"))[:240]
    if not url or not title:
        return None
    snippet = _clean_text(item.get("snippet") or item.get("description") or item.get("content"))
    engines = item.get("engines")
    engine = item.get("engine") or (engines[0] if isinstance(engines, list) and engines else "")
    try:
        score = float(item.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return {
        "title": title,
        "url": url,
        "snippet": snippet[:MAX_SNIPPET_CHARS],
        "published_at": _clean_text(
            item.get("publishedDate") or item.get("published_at") or item.get("published_date")
        )[:80],
        "engine": _clean_text(engine)[:80],
        "score": score,
        "verification": "search_lead",
    }


def search_web(query: str, limit: int = 8, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Search through the local service and return deduplicated, normalized leads."""
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("搜索词不能为空")
    try:
        bounded_limit = max(1, min(int(limit), MAX_RESULTS))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    url = _with_query(search_service_url(), {"q": clean_query})
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "User-Agent": "xiaoxue-web/local-search-adapter",
        },
    )
    try:
        with urlopen(request, timeout=max(1.0, float(timeout))) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        raise RuntimeError(f"本地搜索服务 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"本地搜索服务不可达：{exc.reason}") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"本地搜索服务返回无效：{type(exc).__name__}") from exc

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _result_rows(payload):
        row = _normalize_result(item)
        if not row or row["url"] in seen:
            continue
        seen.add(row["url"])
        normalized.append(row)
        if len(normalized) >= bounded_limit:
            break
    return normalized


def search_web_payload(query: str, limit: int = 8, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    rows = search_web(query, limit=limit, timeout=timeout)
    return {
        "ok": bool(rows),
        "provider": "local/searxng",
        "query": str(query or "").strip(),
        "count": len(rows),
        "results": rows,
    }


def search_web_json(query: str, limit: int = 8, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    return json.dumps(search_web_payload(query, limit=limit, timeout=timeout), ensure_ascii=False)


def search_service_health(timeout: float = 5.0) -> dict[str, Any]:
    url = search_service_health_url()
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        return {"ok": True, "url": url, "status": "available", "detail": payload}
    except Exception as exc:  # noqa: BLE001 - health result is data, not control flow
        return {"ok": False, "url": url, "status": "unavailable",
                "detail": f"{type(exc).__name__}: {str(exc)[:180]}"}
