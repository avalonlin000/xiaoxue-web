#!/usr/bin/env python3
"""CLI wrapper for Xiaoxue's local free web search.

Usage:
    python3 scripts/search_web.py "TES G2 赛前预测" --limit 8
    python3 scripts/search_web.py --health
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xiaoxue_api.core.web_search import search_service_health, search_web_payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="调用小雪本地免费搜索服务")
    parser.add_argument("query", nargs="?", default="", help="搜索词")
    parser.add_argument("--limit", type=int, default=8, help="结果数，1-50")
    parser.add_argument("--timeout", type=float, default=20.0, help="超时秒数")
    parser.add_argument("--health", action="store_true", help="只检查搜索服务是否可用")
    args = parser.parse_args()

    if args.health:
        result = search_service_health(timeout=min(max(args.timeout, 1.0), 30.0))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if not args.query.strip():
        parser.error("query 不能为空")
    try:
        payload = search_web_payload(args.query, limit=args.limit, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - CLI returns structured failure
        print(json.dumps({"ok": False, "provider": "local/searxng", "query": args.query,
                          "error": f"{type(exc).__name__}: {exc}", "results": []},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
