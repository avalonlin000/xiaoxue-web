#!/usr/bin/env python3
"""小雪联网通道体检：本机搜索 + 备用搜索 + 3 条正文 + 搜索服务状态。

用法：
    python3 scripts/check_web_channels.py
    python3 scripts/check_web_channels.py --json
    python3 scripts/check_web_channels.py --only read

退出码：0 = 跑到的每组里至少有一条通道可用；1 = 整组都断了。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 服务跑在 Hermes 的 venv 里（playwright 装在那边）；换解释器才能测到真实通道。
SERVICE_PYTHON = Path("/home/ubuntu/.hermes/hermes-agent/venv/bin/python")


def _reexec_into_service_python() -> None:
    if os.environ.get("XIAOXUE_CHANNEL_CHECK") == "1" or not SERVICE_PYTHON.is_file():
        return
    try:
        import playwright  # noqa: F401
        return
    except Exception:  # noqa: BLE001
        pass
    if Path(sys.executable).resolve() == SERVICE_PYTHON.resolve():
        return
    os.execve(str(SERVICE_PYTHON), [str(SERVICE_PYTHON), *sys.argv],
              dict(os.environ, XIAOXUE_CHANNEL_CHECK="1"))


_reexec_into_service_python()

from xiaoxue_api.modules.match.event import collection_repository as repo  # noqa: E402
from xiaoxue_api.core.web_search import search_service_health  # noqa: E402

SEARCH_QUERY = "TES G2 赛前预测"
ARTICLE_URL = "https://www.oneesports.gg/league-of-legends/"

FIX = {
    "local/searxng": "检查 websearch-mcpserver：systemctl status websearch-mcpserver；配置在 /home/ubuntu/.config/websearch/config.yaml",
    "local-service": "本机 8338 搜索服务不可用：systemctl status websearch-mcpserver",
    "bilibili": "B站搜索不用 key，失败多为接口风控，稍后重试即可",
    "domestic/bing": "确认 /home/ubuntu/.local/bin/dsearch 还在、必应网页结构没变",
    "hermes/web": "检查 Hermes web.search_backend=searxng 与 SEARXNG_URL=http://127.0.0.1:8338/searxng",
    "agent-reach/exa": "需要 mcporter + EXA_API_KEY；没配就让它空着，不影响主线",
    "mirror": "r.jina.ai 免费镜像经常被打断，断了不影响主线",
    "exa/fetch": "同 agent-reach/exa",
    "browser": "需要 playwright 与 /snap/bin/chromium；ERR_ABORTED 表示站点拒绝无头访问",
}

CLASSIFY = (
    (("exceeds", "usage limit", "quota", "432", "429", "rate limit"), "额度用尽"),
    (("401", "403", "invalid api key", "unauthorized", "禁止"), "密钥无效"),
    (("未就绪", "不可用", "no such file", "not found"), "缺依赖"),
    (("timeout", "timed out", "budget"), "超时"),
    (("conn", "network", "dns", "unreachable", "refused"), "网络不通"),
)


def _cause(exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    cause = exc.__cause__
    if cause is not None:
        detail += f" <- {type(cause).__name__}: {str(cause)[:140]}"
    return detail.replace("\n", " ")[:220]


def _state(detail: str) -> str:
    text = detail.casefold()
    for words, label in CLASSIFY:
        if any(word in text for word in words):
            return label
    return "失败"


def _count(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError):
        payload = None
    rows = None
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("data") or payload.get("items")
    elif isinstance(payload, list):
        rows = payload
    if isinstance(rows, list):
        return f"{len(rows)} 条结果"
    return f"约 {stdout.count('http')} 条链接"


def _run(name: str, kind: str, fn, arg: str) -> dict:
    started = time.monotonic()
    try:
        output = fn(arg)
    except Exception as exc:  # noqa: BLE001 - 体检把异常收成一行
        detail = _cause(exc)
        return {"name": name, "kind": kind, "ok": False, "seconds": time.monotonic() - started,
                "state": _state(detail), "detail": detail}
    elapsed = time.monotonic() - started
    text = str(output or "")
    if not text.strip():
        return {"name": name, "kind": kind, "ok": False, "seconds": elapsed,
                "state": "空结果", "detail": "返回为空"}
    return {"name": name, "kind": kind, "ok": True, "seconds": elapsed, "state": "可用",
            "detail": f"{len(text)} 字" if kind == "正文" else _count(text)}


def probe_search_service() -> dict:
    started = time.monotonic()
    result = search_service_health(timeout=5.0)
    elapsed = time.monotonic() - started
    return {
        "name": "local-service",
        "kind": "服务",
        "ok": bool(result.get("ok")),
        "seconds": elapsed,
        "state": "可用" if result.get("ok") else "失败",
        "detail": str(result.get("detail") or "")[:220],
    }


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, size: int) -> str:
    return text + " " * max(0, size - _width(text))


def print_table(groups: dict) -> None:
    header = ("通道", "类型", "状态", "耗时", "说明")
    rows = [(r["name"], r["kind"], r["state"], f"{r['seconds']:.1f}s", r["detail"])
            for items in groups.values() for r in items]
    widths = [max(_width(line[i]) for line in [header, *rows]) for i in range(5)]
    print("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(header)))
    print("  ".join("-" * widths[i] for i in range(5)))
    for row in rows:
        print("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)))

    fixes = [(r["name"], FIX.get(r["name"], "")) for items in groups.values()
             for r in items if not r["ok"]]
    if fixes:
        print()
        for name, hint in fixes:
            print(f"  → {name}：{hint or '没有现成修法，先看上面的报错'}")

    parts = []
    for name in ("搜索", "正文"):
        if name not in groups:
            continue
        alive = [r["name"] for r in groups[name] if r["ok"]]
        parts.append(f"{name}可用（{'/'.join(alive)}）" if alive else f"{name}全断")
    if "服务" in groups:
        parts.append("本地搜索服务可用" if groups["服务"][0]["ok"] else f"本地搜索服务{groups['服务'][0]['state']}")
    print()
    print("结论：" + "；".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description="检查小雪联网通道")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--only", choices=("all", "search", "read", "service", "key"), default="all")
    args = parser.parse_args()

    groups: dict = {}
    if args.only in ("all", "search"):
        groups["搜索"] = [
            _run("local/searxng", "搜索", repo._search_via_local, SEARCH_QUERY),
            _run("hermes/web", "搜索", repo._search_via_hermes, SEARCH_QUERY),
            _run("bilibili", "搜索", repo._search_via_bilibili, SEARCH_QUERY),
            _run("domestic/bing", "搜索", repo._search_via_domestic, SEARCH_QUERY),
            _run("agent-reach/exa", "搜索", repo._search_via_exa, SEARCH_QUERY),
        ]
    if args.only in ("all", "read"):
        groups["正文"] = [
            _run("mirror", "正文", repo._read_with_mirror, ARTICLE_URL),
            _run("exa/fetch", "正文", repo._read_with_exa, ARTICLE_URL),
            _run("browser", "正文", repo._read_with_browser, ARTICLE_URL),
        ]
    if args.only in ("all", "service", "key"):
        groups["服务"] = [probe_search_service()]

    ok_map = {name: any(r["ok"] for r in items) for name, items in groups.items()}
    if args.json:
        print(json.dumps({"ok": ok_map, "groups": groups}, ensure_ascii=False, indent=2))
    else:
        print_table(groups)
    return 0 if all(ok for name, ok in ok_map.items() if name in ("搜索", "正文", "服务")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
