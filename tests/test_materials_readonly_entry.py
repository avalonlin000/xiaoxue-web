import sqlite3

from xiaoxue_api.core import database
from xiaoxue_api.modules.match.event import repository, service


def test_empty_match_entry_reads_never_create_business_tables(tmp_path, monkeypatch):
    path = tmp_path / "business.sqlite3"
    sqlite3.connect(path).close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    assert repository.get_workspace("absent") is None
    assert repository.get_trade_plan("absent") is None
    assert repository.get_match_run("absent") is None
    assert repository.get_active_match_run() is None
    assert repository.list_recent_match_runs() == []
    assert repository.list_match_run_entries(1) == []
    assert repository.list_match_run_facts(1) == []
    assert repository.list_match_run_revisions(1) == []
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_reading_finished_active_match_does_not_pause_or_update_user_record(monkeypatch):
    monkeypatch.setattr(repository, "get_active_match_run", lambda: {"id": 1, "activity_status": "active"})
    monkeypatch.setattr(service, "_run_has_finished_result", lambda _: True)
    def reject(*_):
        raise AssertionError("GET must not change user run")
    monkeypatch.setattr(repository, "pause_match_run", reject)
    assert service.get_active_match_run()["exists"] is False


def test_reading_a_trade_plan_never_saves_draft_or_locks_business_record(monkeypatch):
    def reject(*_):
        raise AssertionError("reading materials must not save a trade plan")
    monkeypatch.setattr(repository, "upsert_trade_plan", reject)
    for date in ("2099-01-01", "2000-01-01"):
        identity = service.normalize_match_identity({"team_a": "KC", "team_b": "MVK", "match_date": date, "match_time": "02:00"})
        plan = service._trade_plan_from_row(identity, {"items": []}, None)
        assert plan["state"] == ("draft" if date.startswith("2099") else "locked")


def test_virtual_prematch_desk_redacts_existing_postmatch_materials(monkeypatch):
    from xiaoxue_api.modules.match.event import collection
    monkeypatch.setattr(service, "get_match_context", lambda *_a, **_k: {})
    monkeypatch.setattr(service, "_team_evidence", lambda *_: {})
    monkeypatch.setattr(service, "_match_trading_framework", lambda *_: {})
    monkeypatch.setattr(service, "_trade_plan", lambda *_: {})
    monkeypatch.setattr(service, "_trading_notes", lambda *_: [])
    monkeypatch.setattr(service, "get_match_workspace", lambda *_: {"exists": False})
    monkeypatch.setattr(service, "get_match_run", lambda *_, framework=None: {"exists": True, "mode": "virtual_pre", "result_unlocked": False})
    monkeypatch.setattr(collection, "get_prepared_materials", lambda *_: {"task": {}, "result": {"summary": "赛后结果不得泄露"}})
    data = service.get_match_desk("KC", "MVK", match_date="2026-10-19", match_time="02:00")
    assert data["prepared_materials"]["result"] is None
    assert "回放" in data["prepared_materials"]["notice"]
