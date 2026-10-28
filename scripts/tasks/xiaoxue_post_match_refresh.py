#!/usr/bin/env python3
"""赛后事实刷新（受管任务出口之一）。

由排程器安排在比赛结束预估时刻执行：
1. 跑唯一数据就绪链路（ScoreGG 刷新 + TS 更新 + 数据库门禁）；
2. 读用户可见的范围与覆盖面；
3. 结果出了 → 推一条结果消息；赛后仍未入库 → 推一条告警（不静默）；
4. 结束后调用唯一排程器重排（赛程/结果一有变化就跟着走）。
没有任何要说的内容时保持静默（空输出）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

READINESS = Path("/home/ubuntu/lol_data/scripts/data_readiness_pipeline.py")
PLANNER = Path("/home/ubuntu/lol_data/scripts/lol_auto_planner.py")
STATE_PATH = Path("/home/ubuntu/lol_data/runs/lol_post_facts_state.json")
API = "http://127.0.0.1:8880/api/lol-scope/coverage?date=today&days=2"


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


def fetch_coverage() -> dict:
    with urllib.request.urlopen(API, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize_readiness(result: subprocess.CompletedProcess) -> list[str]:
    """把数据就绪的失败原因说清楚：哪一段失败、退出码、最后一行输出。"""
    if result.returncode == 0:
        return []
    messages = [f"❌ 赛后数据刷新失败（exit {result.returncode}）"]
    raw = (result.stdout or "").strip()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        tail = (raw or (result.stderr or "")).strip()[-600:] or result.stderr or ""
        tail = tail.strip()
        if tail:
            messages.append(tail)
        return messages
    stages = payload.get("stages") or []
    for stage in stages:
        code = stage.get("exit_code")
        if str(stage.get("status")) == "error" or (code not in (0, None)):
            lines = [line for line in str(stage.get("output_tail") or "").strip().splitlines() if line.strip()]
            detail = lines[-1] if lines else ""
            messages.append(f"  失败段：{stage.get('id')}（exit {code}）{detail[:300]}")
    errors = list((payload.get("readiness") or {}).get("errors") or [])
    for error in errors[:5]:
        messages.append(f"  就绪检查：{error}")
    if len(messages) == 1:
        messages.append("  未返回具体失败段，请查看数据就绪 manifest")
    return messages


def main() -> int:
    messages: list[str] = []

    if READINESS.is_file():
        refresh = subprocess.run([sys.executable, str(READINESS)], capture_output=True, text=True, cwd=str(READINESS.parent))
        messages.extend(summarize_readiness(refresh))
    else:
        messages.append(f"❌ 数据就绪链路缺失：{READINESS}")

    try:
        payload = fetch_coverage()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        messages.append(f"⚠️ 赛后覆盖面读取失败：{exc}")
        payload = {}

    state = load_state()
    results_state = dict(state.get("results") or {})
    for item in payload.get("matches") or []:
        key = str(item.get("match_key") or "")
        result = item.get("result") or {}
        status = str(result.get("status") or "")
        previous = results_state.get(key)
        if status == "ok" and previous != "ok":
            messages.append(f"✅ 结果出了：{item.get('label')} → {result.get('detail')}（{str(result.get('recorded_at') or '')[:16]}）")
        elif status == "missing":
            messages.append(f"⚠️ 赛后仍未入库：{item.get('label')}（{item.get('time')}）")
        if key:
            results_state[key] = status
    state["results"] = results_state
    state["checked_at"] = payload.get("date_from") or ""

    if PLANNER.is_file():
        plan = subprocess.run([sys.executable, str(PLANNER)], capture_output=True, text=True, cwd=str(PLANNER.parent))
        if plan.returncode != 0:
            detail = ((plan.stdout or "") + (plan.stderr or "")).strip()[-400:]
            messages.append(f"⚠️ 赛后重排失败，排程可能停在旧时刻{('：' + detail) if detail else ''}")

    save_state(state)
    if messages:
        print("\n".join(messages))
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_post_match_refresh.py（无参数；赛后刷新与重排）")
        raise SystemExit(0)
    raise SystemExit(main())
