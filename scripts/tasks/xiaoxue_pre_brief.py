#!/usr/bin/env python3
"""赛前简报（受管任务出口之一）。

由排程器安排在开打前约 90 分钟执行：只说今天看什么、缺什么。
读数是用户可见的同一入口（工作台 API 的范围与覆盖面），不另建第二套事实。
无比赛或无范围内容 → 静默（空输出）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
import urllib.error
import urllib.request

API = "http://127.0.0.1:8880/api/lol-scope/coverage?date=today&days=2"
STATUS_LABEL = {"ok": "齐", "stale": "陈旧", "missing": "缺", "pending": "待"}


def fetch() -> dict:
    with urllib.request.urlopen(API, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        payload = fetch()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        print(f"⚠️ 赛前简报取数失败：{exc}")
        return 0
    matches = payload.get("matches") or []
    if not matches:
        return 0
    now = datetime.now()
    upcoming: list[tuple[datetime, dict]] = []
    for item in matches:
        try:
            start = datetime.strptime(str(item.get("time") or "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        # 只发还没开打的场次；已开打/已出结果的一律不再进入“赛前简报”。
        if start <= now:
            continue
        if (item.get("result") or {}).get("status") == "ok":
            continue
        upcoming.append((start, item))
    if not upcoming:
        return 0
    next_day = min(start.date() for start, _ in upcoming)
    upcoming = [(start, item) for start, item in upcoming if start.date() == next_day]
    scope = payload.get("event") or "当前赛事"
    lines = [f"⏰ 赛前简报｜{scope}"]
    for start, item in upcoming:
        lineup = item.get("lineup") or {}
        price = item.get("price") or {}
        result = item.get("result") or {}
        lines.append(
            f"{start.strftime('%m-%d %H:%M')} {item.get('label')}"
            f"（{item.get('format') or ''}）"
            f"｜谁上场 {STATUS_LABEL.get(lineup.get('status'), lineup.get('status'))}"
            f"｜价格 {STATUS_LABEL.get(price.get('status'), price.get('status'))}"
            f"｜结果 {STATUS_LABEL.get(result.get('status'), result.get('status'))}"
        )
        sides = (lineup.get("sides") or {})
        detail = "；".join(
            f"{side} {value.get('detail')}" for side, value in sides.items() if value.get("status") in ("stale", "missing")
        )
        if detail:
            lines.append(f"  洞：{detail}")
    gap_count = sum(len(item.get("gaps") or []) for _, item in upcoming)
    lines.append(f"（{len(upcoming)} 场比赛，{gap_count} 项缺口）")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_pre_brief.py（无参数；生成赛前简报）")
        raise SystemExit(0)
    raise SystemExit(main())
