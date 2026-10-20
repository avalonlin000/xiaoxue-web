import importlib.util
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import sys
from unittest.mock import Mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_match_materials.py"
spec = importlib.util.spec_from_file_location("materials_scheduler_cli", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def task(index, state="queued", **changes):
    return {"id": f"{index:024x}", "state": state, "attempts": 0,
            "created_at": "2026-10-20T00:00:00+00:00", **changes}


def setup_tick(monkeypatch, tmp_path, tasks):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "prepare_scope_batch", Mock(return_value={"event": "S16", "tasks": tasks, "skipped": []}))
    monkeypatch.setattr(cli, "prepare_upcoming", Mock(return_value={"event": "S16", "tasks": [], "skipped": []}))
    monkeypatch.setattr(cli, "get_collection_task", lambda key: {"task": next(row for row in tasks if row["id"] == key), "result": None})
    monkeypatch.setattr(cli, "_spawn_worker", Mock(return_value=None))


def test_tick_enqueues_all_scopes_and_matches_but_only_dispatches_two(monkeypatch, tmp_path):
    tasks = [task(index) for index in range(5)]
    setup_tick(monkeypatch, tmp_path, tasks)
    result = cli.scheduler_tick()
    cli.prepare_scope_batch.assert_called_once_with(dispatch=False)
    cli.prepare_upcoming.assert_called_once_with(hours=24, dispatch=False)
    assert len(result["dispatched"]) == 2
    assert cli._spawn_worker.call_count == 2
    assert result["queued"] == 5


def test_live_worker_slots_stop_second_tick_starting_more_workers(monkeypatch, tmp_path):
    setup_tick(monkeypatch, tmp_path, [task(index) for index in range(3)])
    locks = []
    for slot in range(2):
        path = tmp_path / ".scheduler" / f"worker-{slot}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    try:
        assert cli.scheduler_tick()["dispatched"] == []
        cli._spawn_worker.assert_not_called()
    finally:
        for handle in locks:
            handle.close()


def test_tick_preserves_partial_generation_until_recovery_is_due(monkeypatch, tmp_path):
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    rows = [task(1, "partial", attempts=1, next_recovery_at=(now + timedelta(minutes=10)).isoformat()),
            task(2, "partial", attempts=2, next_recovery_at=(now - timedelta(seconds=1)).isoformat()),
            task(3, "failed", attempts=3, next_recovery_at=now.isoformat())]
    setup_tick(monkeypatch, tmp_path, rows)
    def resume(key, **kwargs):
        assert kwargs == {"dispatch": False}
        rows[1]["state"] = "queued"
        return {"task": rows[1], "result": None}
    recover = Mock(side_effect=resume)
    monkeypatch.setattr(cli, "resume_collection", recover)
    result = cli.scheduler_tick(now_value=now)
    recover.assert_called_once_with(rows[1]["id"], dispatch=False)
    assert result["dispatched"] == [rows[1]["id"]]
    assert rows[0]["state"] == "partial" and rows[2]["attempts"] == 3


def test_tick_skips_live_leases_and_completed_outputs(monkeypatch, tmp_path):
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    rows = [task(1, "running", attempts=1, lease_until=(now + timedelta(minutes=5)).isoformat()),
            task(2, "completed"), task(3, "running", attempts=1, lease_until=(now - timedelta(seconds=1)).isoformat())]
    setup_tick(monkeypatch, tmp_path, rows)
    result = cli.scheduler_tick(now_value=now)
    assert result["dispatched"] == [rows[2]["id"]]


def test_partial_without_retry_deadline_is_not_restarted_by_periodic_tick(monkeypatch, tmp_path):
    setup_tick(monkeypatch, tmp_path, [task(1, "partial", attempts=1, next_recovery_at="")])
    resume = Mock(side_effect=AssertionError("证据空缺不等于失败恢复"))
    monkeypatch.setattr(cli, "resume_collection", resume)
    assert cli.scheduler_tick()["dispatched"] == []
    resume.assert_not_called()


def test_near_match_is_prioritized_ahead_of_team_backfill(monkeypatch, tmp_path):
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    rows = [task(1), task(2), task(3, match={"match_date": "2026-10-20", "match_time": "09:00"})]
    setup_tick(monkeypatch, tmp_path, rows)
    result = cli.scheduler_tick(now_value=now)
    assert result["dispatched"] == [rows[2]["id"], rows[0]["id"]]


def test_tick_is_nonblocking_when_another_scheduler_is_planning(monkeypatch, tmp_path):
    setup_tick(monkeypatch, tmp_path, [])
    directory = tmp_path / ".scheduler"
    directory.mkdir()
    with (directory / "tick.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.scheduler_tick()["status"] == "already_checking"
    cli.prepare_scope_batch.assert_not_called()


def test_worker_command_inherits_the_cross_process_slot(monkeypatch, tmp_path):
    lock = (tmp_path / "slot.lock").open("a")
    spawn = Mock()
    monkeypatch.setattr(cli.subprocess, "Popen", spawn)
    try:
        cli._spawn_worker(task(1)["id"], lock)
        args, kwargs = spawn.call_args
        assert "run_collection_bounded" in " ".join(args[0])
        assert "worker_slot_fd=int(sys.argv[3])" in args[0][2]
        assert args[0][2].index("os.close") < args[0][2].index(";scheduler_tick()")
        assert kwargs["pass_fds"] == (lock.fileno(),)
        assert kwargs["start_new_session"] is True
    finally:
        lock.close()


def test_manual_worker_reuses_held_slot_instead_of_claiming_another(monkeypatch, tmp_path):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path))
    called = []
    def run(key, *, worker_slot_fd):
        assert key == task(1)["id"]
        # The inherited descriptor remains open/locked until the bounded task
        # finishes; canonical collection validates this fd rather than waiting
        # for a second worker slot held by its own parent.
        called.append(worker_slot_fd)
        held = cli._try_lock(tmp_path / ".scheduler" / "worker-0.lock")
        assert held is None
    monkeypatch.setattr(cli, "run_collection_bounded", run)
    cli._run_with_slot(task(1)["id"])
    assert len(called) == 1
    released = cli._try_lock(tmp_path / ".scheduler" / "worker-0.lock")
    assert released is not None
    released.close()


def test_scheduler_flag_does_not_accept_refresh_or_manual_scope(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--scheduler-tick", "--refresh"])
    assert cli.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
