import copy
from unittest.mock import patch

import pytest

from xiaoxue_api.modules.current_event import collection, collection_repository as repository
from xiaoxue_api.modules.current_event.analysis_repository import analyze_scope as real_analyze_scope
from xiaoxue_api.modules.current_event.collection_repository import dependency_manifest as real_dependency_manifest


@pytest.fixture(autouse=True)
def no_live_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "isolated-materials"))
    for name in ("search", "read_article", "call_digest_model"):
        monkeypatch.setattr(repository, name, lambda *args, **kwargs: pytest.fail("单测禁止真实网络或模型请求"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    manifest = {"internal": "profile-v1", "library": "library-v1", "external": "sources-v1", "analysis": "methods-v1"}
    monkeypatch.setattr(repository, "dependency_manifest", lambda _: copy.deepcopy(manifest))
    monkeypatch.setattr("xiaoxue_api.modules.current_event.analysis_repository.analyze_scope", lambda *_: ([], []))
    return manifest


def complete_scope():
    values = {"scope": "team", "event": "S16", "team": "KC"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    rows = [{"id": "team_KC", "items": [{"text": "KC依靠边线压力取得先动权", "verification": "internal_record", "applicability": "unverified"}]}]
    digest = [{"id": "digest", "selection_status": "screened", "summary": "队伍分析已筛选", "items": [{"text": "KC新赛段依靠边线压力取得先动权", "kind": "author_analysis", "evidence_quote": "KC relies on side lane pressure", "source_id": "body-1", "related_teams": ["KC"], "published_at": repository.now()}]}]
    with patch.object(repository, "collect_scope_internal", return_value=(rows, [])), patch.object(repository, "collect_external", return_value=([], [])), patch.object(repository, "summarize_materials", return_value=(digest, [])):
        collection.run_collection(task["id"])
    return values, task


def test_profile_revision_invalidates_only_internal_not_external_digest(store):
    values, task = complete_scope()
    store["internal"] = "profile-v2"
    updated = collection.prepare_scope(values, dispatch=False)["task"]
    assert updated["generation"] == task["generation"] + 1
    stages = repository.read_checkpoint(updated)["stages"]
    assert "internal" not in stages
    assert "external" in stages and "digest" in stages
    with patch.object(repository, "collect_scope_internal", return_value=([{"id": "team_KC", "items": [{"text": "修订后的KC画像"}]}], [])) as internal, patch.object(repository, "collect_external", side_effect=AssertionError("不重复外搜")), patch.object(repository, "summarize_materials", side_effect=AssertionError("不重复粗筛")):
        collection.run_collection(updated["id"])
    assert internal.call_count == 1
    assert collection.get_scope_materials(values)["result"]["revision"]


def test_unchanged_dependencies_reuse_result_without_new_generation(store):
    values, task = complete_scope()
    assert collection.prepare_scope(values, dispatch=False)["task"]["generation"] == task["generation"]


def test_source_revision_invalidates_external_digest_but_keeps_internal(store):
    values, _ = complete_scope()
    store["external"] = "sources-v2"
    task = collection.prepare_scope(values, dispatch=False)["task"]
    stages = repository.read_checkpoint(task)["stages"]
    assert set(stages) == {"internal"}


def test_coverage_does_not_count_global_version_or_roster_as_team_content(store):
    config = {"event": "S16", "confirmed_teams": ["KC", "GEN"], "participants_verified": True}
    values = {"scope": "team", "event": "S16", "team": "KC"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish(worker, {"subject": worker["subject"], "status": "partial", "updated_at": repository.now(), "sections": [{"id": "version", "items": [{"text": "全局版本理解"}]}, {"id": "team_KC", "items": [{"text": "选手A、选手B", "source": "已登记选手"}]}]})
    with patch.object(collection, "get_current_event", return_value=config):
        coverage = collection.get_scope_coverage()
    assert coverage["teams_total"] == 2
    assert coverage["teams_readable"] == 0
    assert coverage["all_teams_readable"] is False
    assert coverage["items"][1]["readable"] is False


def test_batch_coverage_tracks_real_team_content_and_missing_team(store):
    complete_scope()
    config = {"event": "S16", "confirmed_teams": ["KC", "GEN"], "participants_verified": False}
    with patch.object(collection, "get_current_event", return_value=config):
        batch = collection.prepare_scope_batch(dispatch=False)
    coverage = batch["coverage"]
    assert coverage["teams_readable"] == 1
    assert coverage["all_teams_readable"] is False
    assert coverage["participants_verified"] is False
    assert coverage["items"][1]["team"] == "KC" and coverage["items"][1]["author_analysis_count"] == 1


def test_team_alias_focus_finds_late_fullname_analysis_not_first_8000_chars(store):
    body = "Unrelated tournament introduction. " * 400 + "\n\n## Team Liquid\n\n" + "Team Liquid force the opposition to react to side lane pressure before grouped fights. " * 8
    config = {"event": "S16", "aliases": ["Worlds 2026"], "team_aliases": {"TLAW": ["Team Liquid"]}, "source_hints": [{"url": "https://example.com/all-teams", "title": "All teams analysis", "source_category": "author_analysis"}]}
    with patch("xiaoxue_api.modules.current_event.service.get_current_event", return_value=config), patch.object(repository, "search", return_value=([], "")), patch.object(repository, "read_article", return_value=body):
        rows, _ = repository.collect_external({"scope": "team", "event": "S16", "team": "TLAW", "reference_date": "2026-10-20"})
    assert len(rows) == 1
    assert "Team Liquid force" in rows[0]["text"]
    assert len(rows[0]["text"]) <= 8000
    assert rows[0]["body"] == body


def test_scope_analysis_executes_original_method_without_fake_match(store):
    import json
    from xiaoxue_api.modules.current_event import analysis_repository as analysis

    sections = [{"id": "version", "items": [{"text": "旧26.16认识", "applicability": "unverified"}]}, {"id": "digest", "items": [{"text": "官方26.20版本调整", "kind": "reported_information", "source_category": "official_background", "evidence_quote": "Patch 26.20 changes", "source_id": "source1"}]}]
    response = {"items": [{"method_id": "version", "text": "旧26.16认识需要在26.20重新检验。", "basis": "官方已明确比赛版本变化", "confirmation": "新版本比赛出现对应效果", "invalidation": "旧赢法不再适配", "source_ids": ["I1", "I2"]}]}
    with patch.object(repository, "call_digest_model", return_value=json.dumps(response, ensure_ascii=False)) as model:
        outputs, missing = real_analyze_scope({"scope": "event", "event": "S16"}, sections)
    assert not missing
    packet = model.call_args.args[0]
    assert packet["operation"] == "scope_analysis" and "match" not in packet
    assert outputs[0]["items"][0]["inference_scope"] == "conditional"
    assert outputs[0]["items"][0]["method_version"]


def test_unchanged_refetched_bodies_reuse_digest_without_model(store):
    values, _ = complete_scope()
    store["external"] = "sources-v2"
    task = collection.prepare_scope(values, dispatch=False)["task"]
    with patch.object(repository, "collect_scope_internal", side_effect=AssertionError("不重复已有输入")), patch.object(repository, "collect_external", return_value=([], [])), patch.object(repository, "summarize_materials", side_effect=AssertionError("正文未变不重跑模型")) as model:
        collection.run_collection(task["id"])
    assert model.call_count == 0
    assert collection.get_scope_materials(values)["result"]["delivery"]["public_author_analysis"] == "available"


def test_scheduler_submission_does_not_reset_pending_recovery_attempt(store):
    values = {"scope": "event", "event": "S16"}
    task = collection.prepare_scope(values, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish(worker, None)
    repeated = collection.prepare_scope(values, dispatch=False)["task"]
    assert repeated["generation"] == task["generation"] and repeated["attempts"] == 1


def test_old_profile_is_only_background_not_current_team_coverage(store):
    config = {"event": "S16", "confirmed_teams": ["KC"]}
    task = collection.prepare_scope({"scope": "team", "event": "S16", "team": "KC"}, dispatch=False)["task"]
    worker = repository.claim(task["id"])
    repository.finish(worker, {"subject": worker["subject"], "status": "partial", "updated_at": repository.now(), "sections": [{"id": "team_KC", "items": [{"text": "旧人员旧版本画像", "source": "已有画像", "content_hash": "old", "applicability": "unverified"}]}]})
    with patch.object(collection, "get_current_event", return_value=config):
        assert collection.get_scope_coverage()["teams_readable"] == 0


def test_team_scope_skips_event_only_seeds_and_stops_after_two_real_team_sources(store):
    config = {"event": "S16", "source_hints": [{"url": "https://example.com/version", "scopes": ["event"]}, {"url": "https://example.com/team1", "source_category": "author_analysis", "scopes": ["team"]}, {"url": "https://example.com/team2", "source_category": "author_analysis", "scopes": ["team"]}]}
    body = "KC control side lane waves before contesting neutral objectives. " * 10
    with patch("xiaoxue_api.modules.current_event.service.get_current_event", return_value=config), patch.object(repository, "read_article", side_effect=[body, body + " Extra independent explanation."]) as reader, patch.object(repository, "search", side_effect=AssertionError("已有两份团队正文不盲目重搜")) as search:
        rows, _ = repository.collect_external({"scope": "team", "team": "KC", "event": "S16", "reference_date": "2026-10-20"})
    assert reader.call_count == 2
    assert search.call_count == 0
    assert len(rows) == 2


def test_failed_revalidation_keeps_original_timestamp_and_short_negative_cache(store):
    url = "https://example.com/real-source"
    body = "KC published analysis explains its map control and objective setup. " * 8
    with patch.object(repository, "read_article", return_value=body):
        first = repository.read_shared_source(url)
    source_path = repository.root() / "sources" / repository.task_id_for({"match_key": url}) / "body.json"
    record = repository._load(source_path)
    record["captured_at"] = "2026-01-01T00:00:00+00:00"
    repository._save(source_path, record)
    with patch.object(repository, "read_article", side_effect=ValueError("来源受限")) as reader:
        retained = repository.read_shared_source(url)
        second = repository.read_shared_source(url)
    assert reader.call_count == 1
    assert retained["body"] == second["body"] == first["body"]
    assert retained["captured_at"] == "2026-01-01T00:00:00+00:00"
    assert retained["freshness"] == "revalidation_failed"


def test_dependency_manifest_ignores_other_team_and_capture_only_change(store):
    profiles = {"KC": {"profile": {"win_path": "边线"}, "updated_at": "2026-10-18"}, "GEN": {"profile": {"win_path": "资源团"}}}
    with patch("xiaoxue_api.modules.current_event.service.get_current_event", return_value={"event": "S16"}), patch("xiaoxue_api.modules.profiles.public.get_current_profile", side_effect=lambda team: profiles[team]), patch("xiaoxue_api.modules.team_data.public.get_profile_bundle", return_value={}), patch("xiaoxue_api.modules.version_understanding.public.get_global_version_understanding", return_value={}), patch("xiaoxue_api.modules.tk_knowledge.public.browse", return_value={}), patch("xiaoxue_api.modules.tk_knowledge.public.list_match_trading_tk", return_value={}):
        before = real_dependency_manifest({"scope": "team", "event": "S16", "team": "KC"})
        profiles["GEN"]["profile"]["win_path"] = "其他队变化"
        profiles["KC"]["updated_at"] = "2026-10-20"
        after = real_dependency_manifest({"scope": "team", "event": "S16", "team": "KC"})
        profiles["KC"]["profile"]["win_path"] = "本队变化"
        changed = real_dependency_manifest({"scope": "team", "event": "S16", "team": "KC"})
    assert before == after
    assert before["internal"] != changed["internal"]


def test_public_evidence_missing_is_not_scheduled_as_model_failure(store):
    task = collection.prepare_scope({"scope": "event", "event": "S16"}, dispatch=False)["task"]
    with patch.object(repository, "collect_scope_internal", return_value=([{"id": "version", "items": [{"text": "旧版本"}]}], [])), patch.object(repository, "collect_external", return_value=([], [])), patch.object(repository, "summarize_materials", return_value=([], [])), patch("xiaoxue_api.modules.current_event.analysis_repository.analyze_scope", side_effect=real_analyze_scope), patch.object(repository, "call_digest_model", side_effect=AssertionError("无公开证据不重跑模型")):
        collection.run_collection(task["id"])
    assert not repository.read(task["id"])["task"]["next_recovery_at"]


def test_shared_worker_slot_reuses_only_own_fd_and_does_not_close_it(store):
    import os

    with repository.collection_worker_slot() as fd:
        with repository.collection_worker_slot(fd) as reused:
            assert reused == fd
        os.fstat(fd)
        with (repository.root() / "wrong-slot").open("a") as other:
            with pytest.raises(ValueError):
                with repository.collection_worker_slot(other.fileno()):
                    pass
