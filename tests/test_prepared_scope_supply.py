from unittest.mock import patch

import pytest

from xiaoxue_api.modules.current_event import collection, collection_repository as repository


@pytest.fixture(autouse=True)
def no_live_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "isolated-materials"))
    for name in ("search", "read_article", "call_digest_model"):
        monkeypatch.setattr(repository, name, lambda *args, **kwargs: pytest.fail("单测禁止真实网络或模型请求"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    monkeypatch.setattr("xiaoxue_api.modules.current_event.analysis_repository.analyze_scope", lambda *_: ([], []))
    monkeypatch.setattr(repository, "dependency_manifest", lambda _: {"internal": "test", "library": "test", "external": "test", "analysis": "test"})
    return tmp_path / "materials"


def test_team_preparation_exists_without_a_scheduled_opponent(store):
    values = {"scope": "team", "event": "S16", "team": "KC"}
    assert collection.get_scope_materials(values) == {"task": None, "result": None}
    assert not store.exists()
    task = collection.prepare_scope(values, dispatch=False)["task"]
    assert task["subject"]["team"] == "KC"
    assert "match" not in task
    assert "team_b" not in task["subject"]
    with patch.object(repository, "collect_scope_internal", return_value=([{"id": "team_KC", "items": [{"text": "KC当前已有队伍内容"}]}], [])), patch.object(repository, "collect_external", return_value=([], [])), patch.object(repository, "summarize_materials", return_value=([], [])):
        collection.run_collection(task["id"])
    result = collection.get_scope_materials(values)["result"]
    assert result["subject"]["scope"] == "team"
    assert result["sections"][0]["items"][0]["text"] == "KC当前已有队伍内容"
    assert result["delivery"]["ready"] is False
    assert "match" not in result


def test_scope_batch_uses_confirmed_participants_not_existing_fixtures(store):
    config = {"event": "S16", "participants": ["KC", "GEN", "TBD", "KC"]}
    with patch.object(collection, "get_current_event", return_value=config), patch.object(collection, "list_schedules", side_effect=AssertionError("参赛队预备不依赖赛程")):
        batch = collection.prepare_scope_batch(dispatch=False)
    assert [task["subject"]["scope"] for task in batch["tasks"]] == ["event", "team", "team"]
    assert [task["subject"].get("team") for task in batch["tasks"][1:]] == ["KC", "GEN"]
    assert batch["participants_verified"] is False


def test_exact_shared_body_is_fetched_once_and_repost_is_one_item(store):
    identity = {"team_a": "KC", "team_b": "GEN", "event": "S16", "match_date": "2099-10-20"}
    body = "KC GEN " + "两队教练分析当前打法及运营变化，其依据来自本阶段近期比赛。" * 15
    leads = [{"url": "https://example.com/analysis", "title": "KC分析", "published_at": "2099-10-19"}, {"url": "https://another.example/analysis", "title": "同文转载", "published_at": "2099-10-19"}]
    with patch.object(repository, "search", return_value=(leads, "")), patch.object(repository, "read_article", return_value=body) as reader:
        first, _ = repository.collect_external(identity)
        second, _ = repository.collect_external({**identity, "team_b": "BLG"})
    assert reader.call_count == 2
    assert len(first) == len(second) == 1
    assert len(first[0]["source_urls"]) == 2


def test_scope_identity_rejects_empty_or_placeholder_team(store):
    for team in ("", "TBD", "待定"):
        with pytest.raises(ValueError):
            collection.prepare_scope({"scope": "team", "event": "S16", "team": team}, dispatch=False)
    assert not store.exists()


def test_scope_frozen_read_has_no_future_content_or_mutation(store):
    values = {"scope": "event", "event": "S16"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish(worker, {"subject": worker["subject"], "updated_at": "2026-10-20T10:00:00+00:00", "status": "partial", "sections": [{"id": "news", "items": [{"text": "十点取得内容"}]}]})
    before = {path: path.stat().st_mtime_ns for path in store.rglob("*") if path.is_file()}
    assert collection.get_scope_materials(values, as_of="2026-10-20T09:59:00+00:00")["result"] is None
    frozen = collection.get_scope_materials(values, as_of="2026-10-20T10:01:00+00:00")
    assert frozen["task"]["subject"]["scope"] == "event"
    assert {path: path.stat().st_mtime_ns for path in store.rglob("*") if path.is_file()} == before


def test_internal_scope_does_not_claim_legacy_version_or_profile_is_current(store):
    profile = {"found": True, "updated_at": "2026-07-01", "profile": {"win_path": "旧版本运营取胜"}}
    version = {"status": "ok", "data": {"item": {"id": 229, "created_at": "2026-07-01", "content": "旧版本理解"}}}
    with patch("xiaoxue_api.modules.profiles.public.get_current_profile", return_value=profile), patch("xiaoxue_api.modules.version_understanding.public.get_global_version_understanding", return_value=version), patch("xiaoxue_api.modules.team_data.public.get_profile_bundle", return_value={}):
        sections, limitations = repository.collect_scope_internal({"scope": "team", "event": "S16", "team": "KC"})
    items = [item for section in sections for item in section["items"]]
    assert all(item["applicability"] == "unverified" and item["recognition"] == "unknown" for item in items)
    assert all("已认可" not in item["source"] for item in items)
    assert "尚未核对" in " ".join(limitations) or "尚需核对" in " ".join(limitations)


def test_canonical_source_preserves_resource_identity_but_removes_tracking():
    assert repository.canonical_source_url("https://example.com/read?id=42&utm_source=x#view") == "https://example.com/read?id=42"
    with pytest.raises(ValueError):
        repository.canonical_source_url("http://127.0.0.1/private")


def test_scope_digest_has_subject_not_fake_match_and_accepts_timed_update(store):
    import json

    subject = {"scope": "team", "event": "S16", "team": "KC", "reference_date": "2026-10-20"}
    source = {"text": "KC主教练介绍本阶段打法变化和具体的训练调整依据。" * 8, "published_at": "2026-10-19T01:00:00+00:00", "verification": "source_text"}
    response = {"items": [{"text": "教练介绍了本届队伍的打法调整。", "source_ids": ["S1"], "evidence_quote": source["text"][:25], "why_relevant": "说明目前训练及打法的具体变化", "event_key": "kc-style-update", "relevance": "match_update", "kind": "author_analysis"}]}
    with patch.object(repository, "now", return_value="2026-10-20T01:00:00+00:00"), patch.object(repository, "call_digest_model", return_value=json.dumps(response, ensure_ascii=False)) as model:
        sections, missing = repository.summarize_materials(subject, [{"id": "news", "items": [source]}])
    assert "subject" in model.call_args.args[0] and "match" not in model.call_args.args[0]
    assert sections[0]["items"][0]["kind"] == "author_analysis"
    assert not missing


def test_resume_retries_failed_stage_without_resetting_attempt_or_good_stages(store):
    values = {"scope": "team", "event": "S16", "team": "KC"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    with patch.object(repository, "collect_scope_internal", return_value=([{"id": "team_KC", "items": [{"text": "已经取得的正式内容"}]}], [])), patch.object(repository, "collect_external", side_effect=RuntimeError("暂时失败")), patch.object(repository, "summarize_materials", return_value=([], [])):
        collection.run_collection(task["id"])
    failed = repository.read(task["id"])["task"]
    resumed = collection.resume_collection(task["id"], dispatch=False)["task"]
    assert resumed["generation"] == failed["generation"]
    assert resumed["attempts"] == failed["attempts"] == 1
    with patch.object(repository, "collect_scope_internal", side_effect=AssertionError("成功段不得重跑")) as internal, patch.object(repository, "collect_external", return_value=([], [])) as external, patch.object(repository, "summarize_materials", return_value=([], [])):
        collection.run_collection(task["id"])
    assert external.call_count == 1
    assert internal.call_count == 0
    assert repository.read(task["id"])["task"]["attempts"] == 2


def test_repeated_resume_cannot_reset_attempts_and_run_forever(store):
    values = {"scope": "event", "event": "S16"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    with patch.object(repository, "collect_scope_internal", side_effect=RuntimeError("失败")) as internal, patch.object(repository, "collect_external", side_effect=RuntimeError("失败")), patch.object(repository, "summarize_materials", return_value=([], [])):
        for _ in range(6):
            collection.resume_collection(task["id"], dispatch=False)
            collection.run_collection(task["id"])
    assert repository.read(task["id"])["task"]["attempts"] == 3
    assert internal.call_count == 4  # first attempt + one immediate retry + two recoveries


def test_total_budget_stops_before_next_model_and_retains_checkpoint_content(store):
    values = {"scope": "team", "event": "S16", "team": "KC"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    clock = [0.0]

    def external(_):
        clock[0] = 721.0
        return [], []

    with patch.object(repository, "monotonic", side_effect=lambda: clock[0]), patch.object(repository, "collect_scope_internal", return_value=([{"id": "team_KC", "items": [{"text": "预算前取得的内容"}]}], [])), patch.object(repository, "collect_external", side_effect=external), patch.object(repository, "summarize_materials") as model:
        collection.run_collection(task["id"])
    model.assert_not_called()
    data = repository.read(task["id"])
    assert data["result"]["sections"][0]["items"][0]["text"] == "预算前取得的内容"
    assert data["task"]["state"] == "partial"
    assert any("预算" in notice for notice in data["result"]["limitations"])


def test_background_worker_has_real_process_wallclock_and_keeps_attempt(store):
    import sys
    import time

    task = collection.prepare_scope({"scope": "event", "event": "S16"}, dispatch=False)["task"]
    started = time.monotonic()
    with patch.object(collection, "_worker_command", return_value=[sys.executable, "-c", "import time; time.sleep(10)"]):
        collection.run_collection_bounded(task["id"], budget_seconds=0.05)
    assert time.monotonic() - started < 3
    data = repository.read(task["id"])
    assert data["task"]["attempts"] == 1
    assert data["task"]["state"] == "failed"
    assert "预算" in data["task"]["message"]


def test_failed_task_records_ten_then_thirty_minute_bounded_recovery(store):
    from datetime import datetime

    task = collection.prepare_scope({"scope": "event", "event": "S16"}, dispatch=False)["task"]
    for expected_minutes in (10, 30):
        worker = repository.claim(task["id"])
        repository.finish(worker, None, message="来源失败")
        current = repository.read(task["id"])["task"]
        delay = datetime.fromisoformat(current["next_recovery_at"]) - datetime.fromisoformat(current["updated_at"])
        assert delay.total_seconds() == expected_minutes * 60
        collection.resume_collection(task["id"], dispatch=False)
    worker = repository.claim(task["id"])
    repository.finish(worker, None)
    assert not repository.read(task["id"])["task"]["next_recovery_at"]


def test_single_transient_stage_failure_is_retried_once_not_whole_pipeline(store):
    task = collection.prepare_scope({"scope": "event", "event": "S16"}, dispatch=False)["task"]
    rows = [{"id": "version", "items": [{"text": "原本可读的内容"}]}]
    with patch.object(repository, "collect_scope_internal", return_value=(rows, [])) as internal, patch.object(repository, "collect_external", side_effect=[RuntimeError("瞬时失败"), ([], [])]) as external, patch.object(repository, "summarize_materials", return_value=([], [])):
        collection.run_collection(task["id"])
    assert internal.call_count == 1
    assert external.call_count == 2
    assert not repository.read(task["id"])["task"]["next_recovery_at"]


def test_retry_shares_search_budget_instead_of_doubling_it(store):
    identity = {"team_a": "KC", "team_b": "GEN", "event": "S16", "match_date": "2099-10-20"}
    with patch.object(repository, "search", return_value=([], "来源暂不可读")) as search, repository.collection_budget():
        collection._call_stage(repository.collect_external, identity)
    assert search.call_count <= 6


def test_real_background_worker_reads_existing_checkpoint_without_external_calls(store):
    task = collection.prepare_scope({"scope": "event", "event": "S16"}, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.checkpoint(worker, {
        "internal": {"sections": [{"id": "version", "items": [{"text": "已经保存的可读内容"}]}], "limitations": []},
        "external": {"sections": [], "limitations": []},
        "digest": {"sections": [], "limitations": []},
    })
    repository.update_task(task["id"], {"state": "queued", "lease_until": ""})
    collection.run_collection_bounded(task["id"], budget_seconds=10)
    data = repository.read(task["id"])
    assert data["task"]["state"] == "partial"
    assert data["task"]["attempts"] == 2
    assert data["result"]["sections"][0]["items"][0]["text"] == "已经保存的可读内容"


def test_budget_exhaustion_does_not_replace_previous_readable_result(store):
    values = {"scope": "event", "event": "S16"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish(worker, {"subject": worker["subject"], "status": "partial", "updated_at": repository.now(), "sections": [{"id": "digest", "items": [{"text": "上次完整可读成果"}]}]})
    before = repository.read(task["id"])["result"]["revision"]
    task = collection.prepare_scope(values, refresh=True, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish_budget(worker)
    assert repository.read(task["id"])["result"]["revision"] == before


def test_configured_source_hint_and_event_alias_read_real_english_body(store):
    config = {"event": "S16 世界赛", "aliases": ["Worlds 2026"], "source_hints": [{"url": "https://example.com/worlds-analysis", "title": "独立作者分析", "source_category": "author_analysis", "weight": "low"}]}
    body = "Worlds 2026 " + "teams adapt their strategic priorities after reviewing early-game pressure. " * 8
    with patch("xiaoxue_api.modules.current_event.service.get_current_event", return_value=config), patch.object(repository, "search", return_value=([], "")), patch.object(repository, "read_article", return_value=body) as reader:
        rows, _ = repository.collect_external({"scope": "event", "event": "S16 世界赛", "reference_date": "2026-10-20"})
    assert reader.call_count == 1
    assert rows[0]["source_category"] == "author_analysis"
    assert rows[0]["weight"] == "low"
    assert rows[0]["body"] == body


def test_official_background_cannot_be_counted_as_author_analysis(store):
    import json

    source = {"text": "Worlds 2026 event format and dates have been officially announced. " * 5, "verification": "source_text", "source_category": "official_background"}
    response = {"items": [{"text": "官方公布赛事赛制。", "source_ids": ["S1"], "evidence_quote": source["text"][:25], "why_relevant": "说明本届赛事的赛制与时间", "event_key": "worlds-format", "relevance": "useful_background", "kind": "author_analysis"}]}
    with patch.object(repository, "call_digest_model", return_value=json.dumps(response, ensure_ascii=False)):
        sections, _ = repository.summarize_materials({"scope": "event", "event": "S16"}, [{"id": "news", "items": [source]}])
    assert sections[0]["items"][0]["kind"] == "reported_information"
