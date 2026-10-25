from datetime import datetime
from unittest.mock import patch

from xiaoxue_api.modules.match.event import collection, collection_repository as repo


MATCH = {"team_a": "AAA", "team_b": "BBB", "event": "Worlds", "match_date": "2099-10-20", "match_time": "00:30"}


def test_upcoming_prepares_across_midnight_but_not_finished_or_distant_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    rows = [{"team_a": "AAA", "team_b": "BBB", "stage": "Worlds", "date": day, "time": time} for day, time in [
        ("2099-10-19", "20:00"), ("2099-10-20", "2099-10-20 00:30:00"), ("2099-10-20", "23:00")]]
    with patch.object(collection, "get_current_event", return_value={"event": "Worlds"}), patch.object(collection, "list_schedules", return_value=rows) as schedules:
        result = collection.prepare_upcoming(now_value=datetime.fromisoformat("2099-10-19T22:00:00+08:00"), hours=24, dispatch=False)
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["match"]["match_date"] == "2099-10-20"
    assert schedules.call_args.args[0]["date_to"] == "2099-10-20"


def test_frozen_read_uses_older_revision_and_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    for stamp, text in [("2099-10-19T10:00:00+08:00", "赛前旧结论"), ("2099-10-19T15:00:00+08:00", "晚到新结论")]:
        task = collection.prepare_materials(MATCH, refresh=True, dispatch=False)["task"]
        worker = repo.claim(task["id"])
        repo.finish(worker, {"match": worker["match"], "updated_at": stamp, "status": "ok", "sections": [{"id": "analysis", "items": [{"text": text}]}], "limitations": []})
    paths = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    result = collection.get_prepared_materials(MATCH, as_of="2099-10-19T12:00:00+08:00")["result"]
    assert result["sections"][0]["items"][0]["text"] == "赛前旧结论"
    assert paths == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert collection.get_prepared_materials(MATCH, as_of="2099-10-19T09:00:00+08:00")["result"] is None


def test_changed_delivery_meaning_creates_an_immutable_new_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    revisions = []
    for ready in (True, False):
        task = collection.prepare_materials(MATCH, refresh=True, dispatch=False)["task"]
        worker = repo.claim(task["id"])
        repo.finish(worker, {"match": worker["match"], "updated_at": repo.now(), "status": "partial", "sections": [{"id": "analysis", "items": [{"text": "相同正文"}]}], "limitations": [], "delivery": {"ready": ready}})
        revisions.append(repo.read(task["id"])["result"]["revision"])
    assert revisions[0] != revisions[1]
    assert len(list((tmp_path / "materials" / task["id"] / "snapshots").glob("*.json"))) == 2
