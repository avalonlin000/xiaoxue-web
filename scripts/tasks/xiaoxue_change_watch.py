#!/usr/bin/env python3
"""LOL 变化推送（出口之一）：只在真的变了的时候说一句。

盯两件事：
1. 谁上场变了 —— 范围内某场比赛一侧的首发发生变化；
2. 价格到了 —— 某场比赛第一次出现带来源的报价（或报价更新）。

其余内容不进推送，留在库里等你翻。没有变化就完全静默。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("LOL_SCOPE_COVERAGE_URL", "http://127.0.0.1:8880/api/lol-scope/coverage?date=today&days=3")
STATE_PATH = Path(os.environ.get("LOL_CHANGE_WATCH_STATE", "/home/ubuntu/lol_data/runs/lol_change_watch_state.json"))


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(f".{STATE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATE_PATH)


def snapshot(payload: dict) -> dict:
    """把覆盖面里"该推送的两件事"抽成可比较的快照。"""
    result: dict[str, dict] = {}
    for item in payload.get("matches") or []:
        key = str(item.get("match_key") or "") or f"{item.get('label')}@{item.get('time')}"
        sides = {
            str(side): str(value.get("detail") or "")
            for side, value in ((item.get("lineup") or {}).get("sides") or {}).items()
            if value.get("status") in ("ok", "stale", "missing")
        }
        result[key] = {
            "label": str(item.get("label") or ""),
            "time": str(item.get("time") or ""),
            "lineup": sides,
            "price": str((item.get("price") or {}).get("recorded_at") or ""),
            "price_detail": str((item.get("price") or {}).get("detail") or ""),
            "price_source": str((item.get("price") or {}).get("source") or ""),
        }
    return result


def diff_signals(previous: dict, current: dict) -> list[str]:
    """纯函数：对比两次快照，产出要推的消息。"""
    messages: list[str] = []
    for key, now in current.items():
        before = previous.get(key)
        label = now.get("label") or key
        when = str(now.get("time") or "")[5:16]
        if before is None:
            continue
        for side, detail in (now.get("lineup") or {}).items():
            old = (before.get("lineup") or {}).get(side)
            if old is None or old == detail:
                continue
            if "没有在职首发" in old and detail:
                messages.append(f"🔄 谁上场变了｜{label} {when}\n{side}：{detail}（此前没有首发记录）")
            elif detail:
                messages.append(f"🔄 谁上场变了｜{label} {when}\n{side}：{old} → {detail}")
        if now.get("price") and now.get("price") != before.get("price"):
            source = now.get("price_source") or ""
            messages.append(
                f"💰 价格到了｜{label} {when}\n{now.get('price_detail') or ''}"
                f"{('（来源 ' + source + '）') if source else ''}"
            )
    return messages


def main() -> int:
    try:
        with urllib.request.urlopen(API, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        print(f"⚠️ 变化推送取数失败：{exc}")
        return 0
    current = snapshot(payload)
    state = load_state()
    previous = dict(state.get("matches") or {})
    messages = diff_signals(previous, current) if previous else []
    state["matches"] = current
    state["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)
    if messages:
        print("\n\n".join(messages))
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_change_watch.py（无参数；只读比较并更新盯盘状态）")
        raise SystemExit(0)
    raise SystemExit(main())
