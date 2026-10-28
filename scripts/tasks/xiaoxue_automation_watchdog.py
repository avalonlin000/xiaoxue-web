#!/usr/bin/env python3
"""LOL 自动化失败告警（受管任务出口之一）。

每小时检查一次，只在真的有问题时出声：
1. 排程回执是否缺失/过期（排程器本身停了，赛程变化不会再跟随）；
2. 受管任务上次执行是否失败（last_status / failure_streak）；
3. 回执里排了时刻的任务，是不是真的武装好了、真的跑了（计划 ↔ 现实对照）。

判据来自排程器回执，而不是"任务被停用就算故障"：赛前简报 / 赛后刷新是同一个 job
反复改期复用，跑完停在 completed、或本阶段结束后被排程器暂停，都是正常作息；
只有"回执说要跑，但它没武装好 / 没跑"才是故障。
同一问题在 6 小时内不重复打扰；恢复后不再提醒。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

JOBS_PATH = Path.home() / ".hermes" / "cron" / "jobs.json"
RECEIPT_PATH = Path("/home/ubuntu/lol_data/runs/lol_auto_plan.json")
STATE_PATH = Path("/home/ubuntu/lol_data/runs/lol_watchdog_state.json")
PLANNER_JOB = "LOL自动化排程器"
MANAGED = ("LOL赛前简报", "LOL赛后刷新", PLANNER_JOB)
REPEAT_AFTER_SECONDS = 6 * 3600
RECEIPT_MAX_AGE_SECONDS = 26 * 3600
LATE_TOLERANCE = timedelta(minutes=2)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def parse_ts(value) -> datetime | None:
    """解析回执里的 'YYYY-MM-DD HH:MM[:SS]' 和任务里的 ISO 时间，统一成本地 naive 时间。"""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone().replace(tzinfo=None)
    return stamp


def same_minute(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).total_seconds()) < 60


def failure_alert(name: str, job: dict) -> str | None:
    status = str(job.get("last_status") or "")
    streak = int(job.get("failure_streak") or 0)
    if status in {"error", "failed"} or streak > 0:
        detail = str(job.get("last_error") or job.get("last_delivery_error") or "").strip()[:200]
        return f"⚠️ {name} 上次执行失败（{status or 'failure'}）{('：' + detail) if detail else ''}"
    return None


def main() -> int:
    now = time.time()
    now_dt = datetime.now()
    alerts: list[str] = []
    jobs = load_json(JOBS_PATH, {})
    jobs = jobs.get("jobs") if isinstance(jobs, dict) else jobs
    by_name = {str(job.get("name") or ""): job for job in (jobs or [])}

    receipt = load_json(RECEIPT_PATH, None)
    planned: dict[str, dict] = {}
    if receipt is None:
        alerts.append("⚠️ 排程回执缺失：排程器还没有成功跑过")
    else:
        for row in receipt.get("plan") or []:
            if isinstance(row, dict) and row.get("job_name"):
                planned[str(row["job_name"])] = row
        as_of = parse_ts(receipt.get("as_of") or "")
        if as_of is None:
            alerts.append("⚠️ 排程回执时间不可读")
        else:
            age = now - as_of.timestamp()
            if age > RECEIPT_MAX_AGE_SECONDS:
                alerts.append(f"⚠️ 排程回执已过期 {age / 3600:.1f} 小时：排程器可能停了")

    for name in MANAGED:
        job = by_name.get(name)
        if job is None:
            if name == PLANNER_JOB:
                alerts.append(f"⚠️ 受管任务缺失：{name}（自动化没有生效）")
            elif parse_ts((planned.get(name) or {}).get("fire_at") or ""):
                alerts.append(
                    f"⚠️ 受管任务缺失：{name}（回执排了 {(planned.get(name) or {}).get('fire_at')} 要跑）"
                )
            continue
        failed = failure_alert(name, job)
        if failed:
            alerts.append(failed)
        if name == PLANNER_JOB:
            if str(job.get("state")) == "paused" or not job.get("enabled", True):
                alerts.append(f"⚠️ {name} 处于暂停/停用状态，赛程变化不会自动跟随")
            continue

        row = planned.get(name) or {}
        fire_at = parse_ts(row.get("fire_at") or "")
        if fire_at is None:
            continue  # 回执里没有该任务的排程：允许它停在已完成/暂停状态（本阶段无比赛）
        if fire_at > now_dt:
            if str(job.get("state")) == "paused" or not job.get("enabled", True):
                alerts.append(f"⚠️ {name} 排了 {row.get('fire_at')} 却处于暂停/停用状态，到点不会跑")
            elif not same_minute(parse_ts(job.get("next_run_at")), fire_at):
                alerts.append(
                    f"⚠️ {name} 排程与回执不一致：回执 {row.get('fire_at')}，实际 {job.get('next_run_at') or '无'}"
                )
            continue
        last_run = parse_ts(job.get("last_run_at"))
        if last_run is None or last_run < fire_at - LATE_TOLERANCE:
            alerts.append(
                f"⚠️ {name} 到点没跑：回执排的 {row.get('fire_at')}，上次执行 {job.get('last_run_at') or '从未'}"
            )

    state = load_json(STATE_PATH, {})
    alerted = dict(state.get("alerted") or {})
    fresh: list[str] = []
    for alert in alerts:
        last = float(alerted.get(alert) or 0)
        if now - last >= REPEAT_AFTER_SECONDS:
            fresh.append(alert)
            alerted[alert] = now
    keep = {key: value for key, value in alerted.items() if now - float(value) < 7 * 24 * 3600}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(f".{STATE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"alerted": keep}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATE_PATH)

    if fresh:
        print("LOL 自动化告警\n" + "\n".join(fresh))
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_automation_watchdog.py（无参数；只读检查并告警）")
        raise SystemExit(0)
    raise SystemExit(main())
