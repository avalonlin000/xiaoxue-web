#!/usr/bin/env python3
"""Explicit batch entry for the existing scheduler; never installs a cron job."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xiaoxue_api.modules.current_event.public import get_collection_task, prepare_date, prepare_upcoming, prepare_scope, prepare_scope_batch, resume_collection, run_collection_bounded
from xiaoxue_api.modules.current_event.preparation import kickoff


def _scheduler_directory() -> Path:
    root = Path(os.environ.get("XIAOXUE_COLLECTION_DIR", str(Path(__file__).resolve().parents[1] / "data" / "current_event_materials")))
    directory = root / ".scheduler"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _try_lock(path: Path):
    handle = path.open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


@contextmanager
def _worker_slot():
    """Manual batches and scheduler children share the same two process slots."""
    handle = None
    directory = _scheduler_directory()
    while handle is None:
        for slot in range(2):
            handle = _try_lock(directory / f"worker-{slot}.lock")
            if handle is not None:
                break
        if handle is None:
            time.sleep(0.2)
    try:
        yield handle
    finally:
        handle.close()


def _run_with_slot(task_id: str) -> None:
    with _worker_slot() as slot:
        run_collection_bounded(task_id, worker_slot_fd=slot.fileno())


def _spawn_worker(task_id: str, slot) -> None:
    # The parent closes its copy after dispatch; the inherited open-file
    # description keeps this slot locked until the entire bounded job returns.
    # Afterwards one lightweight tick drains the next due work, including newly
    # scheduled matches, rather than blocking the scheduler for a whole team batch.
    script = (
        "import sys,os;sys.path.insert(0,sys.argv[1]);"
        "from scripts.collect_match_materials import run_collection_bounded,scheduler_tick;"
        "run_collection_bounded(sys.argv[2],worker_slot_fd=int(sys.argv[3]));"
        "os.close(int(sys.argv[3]));scheduler_tick()"
    )
    subprocess.Popen([sys.executable, "-c", script, str(Path(__file__).resolve().parents[1]), task_id, str(slot.fileno())],
                     pass_fds=(slot.fileno(),), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def scheduler_tick(*, now_value: datetime | None = None) -> dict:
    """Enqueue through the canonical collector, dispatch without awaiting models.

    Dependency/source invalidation belongs to submit(), not this scheduling
    projection. Recovery preserves that generation and respects its persisted
    10/30-minute deadline. File locks enforce two workers across repeated ticks
    and the existing manual CLI; no cron, messages or business records are made.
    """
    directory = _scheduler_directory()
    lock = _try_lock(directory / "tick.lock")
    if lock is None:
        return {"status": "already_checking", "dispatched": []}
    handles = []
    try:
        now_value = now_value or datetime.now(timezone.utc)
        if now_value.tzinfo is None:
            raise ValueError("调度检查时刻需要包含时区")
        scope = prepare_scope_batch(dispatch=False)
        matches = prepare_upcoming(now_value=now_value, dispatch=False)
        tasks = {row["id"]: row for row in [*scope["tasks"], *matches["tasks"]]}
        pending = []
        for task in tasks.values():
            if int(task.get("attempts") or 0) >= 3:
                continue
            state = task.get("state")
            if state in {"partial", "failed"}:
                due = _timestamp(task.get("next_recovery_at") or "")
                if due is None or due > now_value:
                    continue
                task = resume_collection(task["id"], dispatch=False)["task"]
                state = (task or {}).get("state")
            if state == "running":
                lease = _timestamp(task.get("lease_until") or "")
                if lease and lease > now_value:
                    continue
            if state in {"queued", "running"}:
                pending.append(task)
        def priority(task):
            match = task.get("match") or {}
            try:
                start = kickoff(match)
            except (ValueError, TypeError):
                start = None
            urgent = start is not None and 0 < (start - now_value).total_seconds() <= 7200
            recovery = int(task.get("attempts") or 0) > 0
            return (0 if urgent else 1 if recovery else 2 if not match else 3, start.isoformat() if match and start else "", task.get("created_at") or "", task["id"])
        pending.sort(key=priority)
        dispatched = []
        for slot_number in range(2):
            if not pending:
                break
            slot = _try_lock(directory / f"worker-{slot_number}.lock")
            if slot is None:
                continue
            handles.append(slot)
            task = pending.pop(0)
            _spawn_worker(task["id"], slot)
            dispatched.append(task["id"])
        return {"status": "checked", "event": scope["event"], "queued": len(pending) + len(dispatched),
                "dispatched": dispatched, "truncated": matches.get("truncated", False), "skipped": [*scope.get("skipped", []), *matches.get("skipped", [])]}
    finally:
        for handle in handles:
            handle.close()
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="按已关注赛事准备当天比赛资料，不发布消息、不写个人判断。")
    parser.add_argument("--date", default="today")
    parser.add_argument("--event", default="", help="默认读取当前关注赛事；显式提供时只准备该赛事")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--hours", type=int, help="按当前关注范围提前准备未来N小时，含跨日比赛；不修改排程")
    parser.add_argument("--scope", choices=("event", "team", "all"), help="不等对阵：准备赛事、指定队伍或关注赛事全部已确认参赛队")
    parser.add_argument("--team", default="", help="仅与 --scope team 同用")
    parser.add_argument("--scheduler-tick", action="store_true", help="原排程器的有界检查接点；赛事/队伍/近期比赛共用队列，不安装任务")
    args = parser.parse_args()
    try:
        if args.scheduler_tick:
            if args.scope or args.team or args.refresh or args.hours is not None or args.date != "today" or args.event:
                raise ValueError("调度检查只读当前范围，不与手工范围、刷新或日期参数混用")
            print(json.dumps(scheduler_tick(), ensure_ascii=False))
            return 0
        if args.scope:
            if args.hours is not None or args.date != "today" or (args.scope == "all" and args.event):
                raise ValueError("赛事/队伍预备不与赛程日期、提前窗口参数混用；all只读当前范围")
            if bool(args.team) != (args.scope == "team"):
                raise ValueError("--scope team需要指定--team；其他范围不接受--team")
            if args.scope == "all":
                batch = prepare_scope_batch(refresh=args.refresh, dispatch=False)
            else:
                task = prepare_scope({"scope": args.scope, "event": args.event, "team": args.team}, refresh=args.refresh, dispatch=False)["task"]
                batch = {"event": task["subject"]["event"], "tasks": [task], "skipped": []}
        elif args.team:
            raise ValueError("--team需要与--scope team同用")
        elif args.hours is not None and (args.date != "today" or args.event):
            raise ValueError("提前窗口使用当前关注范围，不与日期/赛事覆盖参数混用")
        else:
            batch = prepare_upcoming(hours=args.hours, refresh=args.refresh, dispatch=False) if args.hours is not None else prepare_date(args.date, event=args.event, refresh=args.refresh, dispatch=False)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(_run_with_slot, [task["id"] for task in batch["tasks"]]))
    states = [get_collection_task(task["id"]) for task in batch["tasks"]]
    print(json.dumps({"date": batch.get("date"), "event": batch["event"], "scope": args.scope or "match", "skipped": batch["skipped"],
                      "participants_verified": batch.get("participants_verified", False),
                      "items": [{"task_id": row["task"]["id"], "state": row["task"]["state"], "summary": (row["result"] or {}).get("summary", row["task"]["message"])} for row in states]}, ensure_ascii=False))
    return 1 if any(row["task"]["state"] == "failed" for row in states) else 0


if __name__ == "__main__":
    raise SystemExit(main())
