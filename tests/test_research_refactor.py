"""User-facing research contracts; all tasks, sources and writers are isolated."""
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import json

import pytest

from xiaoxue_api.modules.match.event import analysis_repository as analysis
from xiaoxue_api.modules.match.event import collection, collection_repository as repo, service

REAL_MANIFEST = repo.dependency_manifest


MATCH = {"team_a": "AAA", "team_b": "BBB", "event": "S16", "match_date": "2099-10-24", "match_time": "18:00"}


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    monkeypatch.setattr(repo, "dependency_manifest", lambda _: {})
    monkeypatch.setattr(service, "get_current_event", lambda: {"event": "S16", "preparation": {"upcoming_days": 7}})
    monkeypatch.setattr(collection, "get_current_event", service.get_current_event)
    for name in ("search", "read_article", "call_digest_model"):
        monkeypatch.setattr(repo, name, lambda *a, **k: pytest.fail("No real network/model in unit tests"))


def article(text="AAA边线压力迫使对手分散", **changes):
    return {"text": text, "kind": "author_analysis", "source_id": "source-1", "evidence_quote": "AAA force opponents to split", "url": "https://example.org/aaa", "related_teams": ["AAA"], **changes}


def test_default_preparation_includes_confirmed_match_outside_48_hours():
    row = {"team_a": "AAA", "team_b": "BBB", "stage": "S16", "date": "2099-10-24", "time": "18:00"}
    with patch.object(collection, "list_schedules", return_value=[row]):
        batch = collection.prepare_upcoming(now_value=datetime.fromisoformat("2099-10-20T10:00:00+08:00"), dispatch=False)
    assert len(batch["tasks"]) == 1
    assert batch["window_end"].startswith("2099-10-27")


def test_eight_match_window_coverage_counts_saved_bodies_and_pending_without_dispatch():
    rows = [{"team_a": f"A{index}", "team_b": f"B{index}", "stage": "S16",
             "date": "2099-10-24", "time": "18:00"} for index in range(8)]
    created = [collection.prepare_materials({"team_a": row["team_a"], "team_b": row["team_b"],
                                              "event": row["stage"], "match_date": row["date"],
                                              "match_time": row["time"]}, dispatch=False)["task"] for row in rows]
    for task, result in zip(created[:2], (
        {"status": "partial", "revision": "partial-r1", "summary": "有正文和缺口", "limitations": ["首发尚未核实"],
         "sections": [{"id": "digest", "selection_status": "screened", "items": [{"text": "已有公开原文"}]}]},
        {"status": "ok", "revision": "ready-r1", "summary": "已取得原文", "limitations": [],
         "delivery": {"ready": True},
         "sections": [{"id": "digest", "selection_status": "screened", "items": [{"text": "已有公开原文"}]}]},
    )):
        repo._save(repo.root() / task["id"] / "latest.json", result)
    repo.update_task(created[1]["id"], {"state": "completed"})
    matches = [{"match": row, "pending": False} for row in rows]
    matches.append({"match": {"team_a": "TBD", "team_b": "TBD", "date": "2099-10-24", "time": "20:00"},
                    "pending": True, "pending_reason": "对阵未定"})
    output = collection.summarize_window_materials(matches)
    assert {key: output[key] for key in ("confirmed_total", "prepared", "partial", "not_started", "pending_total")} == {
        "confirmed_total": 8, "prepared": 1, "partial": 1, "not_started": 6, "pending_total": 1}
    assert output["items"][0]["revision"] == "partial-r1"
    assert output["items"][0]["reason"] == "首发尚未核实"
    assert output["items"][1]["state"] == "prepared"
    assert output["items"][-1]["reason"] == "对阵未定"
    assert all(item["task_id"] for item in output["items"][:8])
    repo.update_task(created[1]["id"], {"state": "queued"})
    refreshed = collection.summarize_window_materials(matches)
    assert refreshed["prepared"] == 0 and refreshed["partial"] == 2
    assert "仍需核对" in refreshed["items"][1]["reason"]


def test_future_match_event_alias_reuses_prepared_task_without_rekeying_old_records():
    config = {"event": "S16 世界赛", "aliases": ["Worlds 2026"], "leagues": ["S16全球总决赛"]}
    source = {**MATCH, "event": "S16全球总决赛"}
    spoken = {**MATCH, "event": "S16 世界赛"}
    with patch.object(collection, "get_current_event", return_value=config):
        first = collection.prepare_materials(source, dispatch=False)
        again = collection.prepare_materials(spoken, dispatch=False)
        english = collection.prepare_materials({**MATCH, "event": "Worlds 2026"}, dispatch=False)
        historical = collection._identity({**spoken, "match_date": "2000-10-24"})
    assert first["task"]["id"] == again["task"]["id"] == english["task"]["id"]
    assert again["task"]["generation"] == first["task"]["generation"]
    assert historical["event"] == "S16 世界赛"
    assert service.normalize_match_identity(spoken)["match_key"] != service.normalize_match_identity(source)["match_key"]


def test_upcoming_dashboard_and_paged_tool_read_same_saved_revision_without_dispatch():
    from xiaoxue_api.modules.match.event import presentation
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    repo._save(repo.root() / task["id"] / "latest.json", {"status": "partial", "revision": "r1",
        "limitations": ["首发未核实"], "summary": "可读正文",
        "sections": [{"id": "digest", "selection_status": "screened", "items": [{"text": "有来源的分析"}]}]})
    source = {"context": {"event": "S16"}, "date": "2099-10-20", "date_to": "2099-10-27",
              "truncated": False, "matches": [{"match": {"team_a": "AAA", "team_b": "BBB",
                "stage": "S16", "date": "2099-10-24", "time": "18:00"}, "pending": False}]}
    with patch.object(presentation, "get_current_event_dashboard", return_value=source):
        dashboard = presentation.current_event_dashboard(date="upcoming", limit=100)
        page = presentation.current_event_preparation_coverage(offset=0, limit=4)
    assert dashboard["preparation"]["items"][0]["revision"] == "r1"
    assert page["items"][0]["revision"] == dashboard["preparation"]["items"][0]["revision"]
    assert page["partial"] == 1 and page["next_offset"] is None
    assert repo.read(task["id"])["task"]["state"] == "queued"


def test_explicit_seven_day_window_accepts_timezone_and_skips_pending():
    rows = [{"team_a": "AAA", "team_b": "BBB", "stage": "S16", "date": "2099-10-24", "time": "2099-10-24T10:00:00Z"},
            {"team_a": "TBD", "team_b": "TBD", "date": "2099-10-24", "time": "19:00"}]
    with patch.object(collection, "list_schedules", return_value=rows):
        batch = collection.prepare_upcoming(hours=168, now_value=datetime.fromisoformat("2099-10-20T10:00:00+08:00"), dispatch=False)
    assert len(batch["tasks"]) == 1 and len(batch["skipped"]) == 1


def test_upcoming_dashboard_queries_configured_range_and_reports_truncation():
    row = {"team_a": "TBD", "team_b": "TBD", "stage": "S16", "date": "2099-10-24", "time": "18:00"}
    with patch.object(service, "list_schedules", return_value=[row]), patch.object(service, "get_current_event_scope_leagues", return_value=["S16"]):
        payload = service.get_current_event_dashboard("2099-10-20", 12)
        upcoming = service.get_current_event_dashboard("upcoming", 12)
    assert payload["date"] == "2099-10-20"
    assert upcoming["date_to"] > upcoming["date"]
    assert upcoming["range"] == "upcoming"
    assert isinstance(upcoming["truncated"], bool)


def test_upcoming_dashboard_uses_the_same_exact_time_window_as_batch_preparation():
    now = datetime.fromisoformat("2099-10-20T10:00:00+08:00")
    rows = [
        {"team_a": "OLD", "team_b": "GAME", "stage": "S16", "date": "2099-10-20", "time": "09:59"},
        {"team_a": "NOW", "team_b": "GAME", "stage": "S16", "date": "2099-10-20", "time": "10:00"},
        {"team_a": "IN", "team_b": "GAME", "stage": "S16", "date": "2099-10-20", "time": "10:01"},
        {"team_a": "EDGE", "team_b": "GAME", "stage": "S16", "date": "2099-10-27", "time": "10:00"},
        {"team_a": "FAR", "team_b": "GAME", "stage": "S16", "date": "2099-10-27", "time": "10:01"},
        {"team_a": "TBD", "team_b": "TBD", "stage": "S16", "date": "2099-10-21", "time": ""},
    ]
    config = {"event": "S16", "leagues": ["S16"], "preparation": {"upcoming_days": 7}}
    with patch.object(service, "get_current_event", return_value=config), \
            patch.object(service, "get_current_event_scope_leagues", return_value=["S16"]), \
            patch.object(service, "list_schedules", return_value=rows):
        upcoming = service.get_current_event_dashboard("upcoming", 12, now_value=now)
    assert {row["match"]["team_a"] for row in upcoming["matches"]} == {"IN", "EDGE", "TBD"}
    assert {row["match"]["team_a"] for row in upcoming["matches"] if row["pending"]} == {"TBD"}


def test_public_evidence_enables_conditional_analysis_without_promoting_old_version():
    sections = [{"id": "digest", "selection_status": "screened", "items": [article()]}]
    response = {"items": [{"method_id": "version", "text": "作者指出边线压力，需核实本场条件。", "basis": "原文分析", "confirmation": "本场出现相同边线条件", "invalidation": "对手处理不同", "source_ids": ["I1"]}]}
    with patch("xiaoxue_api.modules.team.public.get_match_context", return_value={}), patch("xiaoxue_api.modules.knowledge.version.public.get_global_version_understanding", return_value={}), patch.object(repo, "call_digest_model", return_value=json.dumps(response)) as model:
        outputs, missing = analysis.analyze(MATCH, sections)
    assert not missing and outputs
    assert model.call_args.args[0]["inputs"][0]["kind"] == "author_analysis"
    item = outputs[0]["items"][0]
    assert item["inference_scope"] == "conditional"
    assert item["input_evidence"][0]["url"] == "https://example.org/aaa"
    assert item["evidence"][0]["url"] == "https://example.org/aaa"


def test_saved_scope_analysis_exposes_its_actual_sources_without_rewriting_cache():
    subject = collection._scope_identity({"scope": "team", "team": "AAA", "event": "S16"})
    task = repo.submit(subject)["task"]
    source = article(source="作者甲", published_at="2099-10-20", conditions="仅旧版本样本",
                     counterevidence="尚无本届过程证据", applicability="previous_patch", id="I1",
                     content_hash="private-hash", record_id="/home/private/record.md")
    result = {"subject": subject, "status": "partial", "updated_at": "2099-10-20T01:00:00+00:00",
              "revision": "original-r1", "sections": [{"id": "analysis", "items": [
                  {"text": "这是待验证推导。", "input_evidence": [source], "source_ids": ["I1"]}]}]}
    directory = repo.root() / task["id"]
    repo._save(directory / "latest.json", result)
    repo._save(directory / "snapshots" / "old.json", result)
    before = (directory / "latest.json").read_bytes()
    for payload in (repo.read(task["id"]), repo.read_at(task["id"], "2099-10-21T00:00:00+00:00")):
        saved = payload["result"]
        row = saved["sections"][0]["items"][0]["evidence"][0]
        assert row["url"] == source["url"] and row["source"] == "作者甲"
        assert row["conditions"] == "仅旧版本样本" and row["counterevidence"] == "尚无本届过程证据"
        assert row["applicability"] == "previous_patch"
        assert not {"id", "content_hash", "record_id"}.intersection(row)
        assert saved["revision"] == "original-r1"
    assert (directory / "latest.json").read_bytes() == before


def test_readable_analysis_sources_preserve_old_background_without_leaking_audit():
    from xiaoxue_api.modules.match.event.evidence import readable_evidence
    rows = readable_evidence([
        {"text": "旧版本解释，未核实本届适用。", "kind": "version_background", "id": "I9"},
        {"text": "统计结构", "display_text": "双方同口径的近期结果", "kind": "cycle"},
        {"text": "内部文件 /home/private/source.md", "url": "file:///home/private/source.md"},
        {"text": {"raw": "不能展示"}},
        {"text": "公开条目", "url": "https://user:secret@example.org/x", "conditions": {"raw": "不能展示"}},
    ])
    assert rows[0]["kind"] == "version_background" and "未核实" in rows[0]["basis_note"]
    assert rows[1]["text"] == "双方同口径的近期结果"
    raw = json.dumps(rows, ensure_ascii=False)
    assert all(token not in raw for token in ("/home/", "secret", "raw", '"I9"'))


def test_shared_team_digest_is_reused_without_system_inference_feedback():
    from xiaoxue_api.modules.match.event import evidence
    result = {"revision": "r1", "sections": [{"id": "digest", "selection_status": "screened", "items": [article()]}, {"id": "analysis", "items": [{"text": "系统此前猜测"}]}]}
    with patch.object(collection, "get_scope_materials", return_value={"result": result}) as read:
        sections = evidence.prepared_sections(MATCH)
    assert read.call_count == 3
    assert len(sections) == 1 and len(sections[0]["items"]) == 1
    assert "系统此前猜测" not in json.dumps(sections, ensure_ascii=False)


def prepared_article_sections(*, missing_team="", incomplete=False, changed_hash=False, empty_selection=False):
    """Both parent bodies were screened, not merely fetched or summarized elsewhere."""
    from xiaoxue_api.modules.match.event import evidence
    body = {"source_id": "source-1", "content_hash": "a" * 64,
            "verification": "source_text", "url": "https://example.org/aaa",
            "text": "AAA force opponents to split. BBB can challenge the side lane."}

    def read(subject, **_):
        if subject.get("team") not in {"AAA", "BBB"} or subject.get("team") == missing_team:
            return {"result": {}}
        digest = {"id": "digest", "selection_status": "screened", "incomplete": incomplete,
                  "items": [] if empty_selection else [article()]}
        if empty_selection:
            digest["screened_sources"] = [{"source_id": "source-1", "content_hash": body["content_hash"]}]
        return {"result": {"revision": subject["team"] + "-r1", "sections": [
            {"id": "news", "items": [body]}, digest]}}

    with patch.object(collection, "get_scope_materials", side_effect=read):
        shared = evidence.prepared_sections(MATCH)
    current = {**body, "content_hash": "b" * 64} if changed_hash else body
    return [*shared, {"id": "news", "items": [current]}]


def test_unchanged_both_team_sources_are_not_screened_again_for_a_match():
    sections = prepared_article_sections()
    with patch.object(repo, "call_digest_model", side_effect=AssertionError("已筛正文不得再发给模型")):
        outputs, missing = repo.summarize_materials(MATCH, sections)
    assert not outputs[0]["items"] and not missing
    assert "复用" in outputs[0]["summary"]
    assert sections[0]["items"][0]["evidence_quote"] == "AAA force opponents to split"


def test_reused_articles_do_not_hide_new_library_input_from_screening():
    sections = prepared_article_sections() + [{"id": "library", "items": [
        {"text": "新的知识输入有自己的限定。", "verification": "knowledge_extract", "source_id": "tk-new"}]}]
    with patch.object(repo, "call_digest_model", return_value='{"items":[]}') as model:
        _, missing = repo.summarize_materials(MATCH, sections)
    assert not missing
    assert len(model.call_args.args[0]["sources"]) == 1
    assert model.call_args.args[0]["sources"][0]["source_kind"] == "knowledge_extract"


@pytest.mark.parametrize("change", [
    {"missing_team": "BBB"}, {"incomplete": True}, {"changed_hash": True},
])
def test_unproven_or_changed_parent_sources_still_require_match_screening(change):
    with patch.object(repo, "call_digest_model", return_value='{"items":[]}') as model:
        repo.summarize_materials(MATCH, prepared_article_sections(**change))
    assert len(model.call_args.args[0]["sources"]) == 1


def test_fully_screened_empty_selection_is_reusable_without_inventing_evidence():
    sections = prepared_article_sections(empty_selection=True)
    with patch.object(repo, "call_digest_model", side_effect=AssertionError("空筛选结果也不用重筛")):
        outputs, missing = repo.summarize_materials(MATCH, sections)
    assert not outputs[0]["items"] and not missing
    assert not sections[0]["items"]


def test_screening_records_exact_source_body_identity_for_future_reuse():
    source = {"text": "A complete source body.", "verification": "source_text",
              "source_id": "source-1", "content_hash": "a" * 64}
    with patch.object(repo, "call_digest_model", return_value='{"items":[]}'):
        result, _ = repo.summarize_materials(MATCH, [{"id": "news", "items": [source]}])
    assert result[0]["screened_sources"] == [{"source_id": "source-1", "content_hash": "a" * 64}]


@pytest.mark.parametrize("change", ["missing_hash", "old_quote", "revalidation_failed", "historical"])
def test_uncertain_source_identity_never_counts_as_proven_reuse(change):
    sections = prepared_article_sections()
    if change == "missing_hash":
        sections[-1]["items"][0].pop("content_hash")
    elif change == "revalidation_failed":
        sections[-1]["items"][0]["freshness"] = "revalidation_failed"
    elif change == "old_quote":
        sections[0].pop("screened_sources", None)
    identity = {**MATCH, "match_date": "2000-01-01"} if change == "historical" else MATCH
    with patch.object(repo, "call_digest_model", return_value='{"items":[]}') as model:
        repo.summarize_materials(identity, sections)
    assert model.call_count == 1


def test_keywords_in_tk_do_not_generate_a_trade_direction():
    framework = {"items": [{"statement": "稳定，强势，大人头，建议做多", "subject": "AAA", "filename": "note.md"}]}
    assert service._auto_trade_plan(framework, MATCH)["items"] == []


def test_shared_source_keeps_provenance_and_does_not_repeat_conditions():
    from xiaoxue_api.modules.match.event.evidence import public_inputs
    original = article(source_title="作者的原始报道", verification="ai_summary", source="作者甲",
                       applicability="previous_patch", conditions="仅旧版本样本", counterevidence="本场版本未核实")
    first = public_inputs([{"id": "digest", "selection_status": "screened", "items": [original]}])
    second = public_inputs([{"id": "shared_digest", "selection_status": "screened", "items": first}])
    assert second == first
    assert second[0]["source_title"] == original["source_title"]
    assert second[0]["verification"] == "ai_summary"
    assert second[0]["applicability"] == "previous_patch"
    assert second[0]["text"].count("仅旧版本样本") == 1


def test_knowledge_extraction_is_not_upgraded_to_original_source_in_consumers():
    from xiaoxue_api.modules.match.event.evidence import public_inputs, readable_evidence, with_readable_evidence
    item = article(source_kind="knowledge_extract", source="原文中文整理")
    section = {"id": "digest", "selection_status": "screened", "items": [item]}
    original = json.dumps(section)
    selected = public_inputs([section])[0]
    assert selected["source_kind"] == "knowledge_extract"
    assert selected["applicability"] == "unverified_knowledge_extract"
    assert "未复核原文" in selected["source"]
    assert "未复核原文" in readable_evidence([selected])[0]["basis_note"]
    projected = with_readable_evidence({"revision": "frozen-r1", "sections": [section]})
    assert "未复核原文" in projected["sections"][0]["items"][0]["source"]
    assert projected["revision"] == "frozen-r1" and json.dumps(section) == original


def test_pending_digest_and_current_sources_do_not_enter_historical_replay():
    from xiaoxue_api.modules.match.event import evidence
    assert not evidence.public_inputs([{"id": "digest", "selection_status": "pending", "items": [article()]}])
    assert not evidence.public_inputs([{"id": "digest", "items": [article()]}])
    with patch.object(collection, "get_scope_materials", side_effect=AssertionError("不得读取现时资料")):
        assert evidence.prepared_sections({**MATCH, "match_date": "2000-01-01"}) == []


def test_match_cannot_upgrade_media_roster_to_confirmed_starters():
    sections = [{"id": "digest", "selection_status": "screened", "items": [article("媒体预测AAA首发。")]}]
    response = {"items": [{"method_id": "version", "text": "AAA首发已确认。", "basis": "媒体预测名单", "confirmation": "双方进入比赛", "invalidation": "人员变更", "source_ids": ["I1"]}]}
    with patch("xiaoxue_api.modules.team.public.get_match_context", return_value={}), patch("xiaoxue_api.modules.knowledge.version.public.get_global_version_understanding", return_value={}), patch.object(repo, "call_digest_model", return_value=json.dumps(response)):
        outputs, missing = analysis.analyze(MATCH, sections)
    assert not outputs and missing


def test_cycle_evidence_does_not_promote_public_version_analysis_to_supported():
    inputs = [{"id": "I1", **article()}, {"id": "I2", "kind": "cycle", "comparable": True, "text": "双方周期同口径"}]
    response = {"items": [{"method_id": "version", "text": "作者所说的边线条件需要复核。", "basis": "公开观点", "confirmation": "本场出现相同条件", "invalidation": "本场条件不同", "source_ids": ["I1"]}]}
    with patch.object(analysis, "collect_inputs", return_value=inputs), patch.object(repo, "call_digest_model", return_value=json.dumps(response)) as model:
        outputs, _ = analysis.analyze(MATCH, [{"id": "digest", "items": [article()]}])
    assert outputs[0]["items"][0]["inference_scope"] == "conditional"
    assert next(row for row in model.call_args.args[0]["methods"] if row["id"] == "version")["inference_scope"] == "conditional"


def test_date_entry_uses_canonical_schedule_league_not_display_event_name():
    config = {"event": "S16 世界赛", "leagues": ["S16全球总决赛"]}
    row = {"team_a": "AAA", "team_b": "BBB", "stage": "S16全球总决赛", "date": "2099-10-24", "time": "18:00"}
    with patch.object(collection, "get_current_event", return_value=config), patch.object(collection, "list_schedules", return_value=[row]) as read:
        report = collection.prepare_date("2099-10-24", dispatch=False)
    assert report["tasks"]
    assert read.call_args.args[0]["event"] == "S16全球总决赛"
    assert report["truncated"] is False


def test_shared_dependency_tracks_source_meaning_not_generated_analysis_revision():
    result = {"revision": "r1", "sections": [{"id": "digest", "selection_status": "screened", "items": [article()]}]}
    with patch("xiaoxue_api.modules.team.public.get_current_profile", return_value={}), patch("xiaoxue_api.modules.team.public.get_profile_bundle", return_value={}), patch("xiaoxue_api.modules.knowledge.version.public.get_global_version_understanding", return_value={}), patch("xiaoxue_api.modules.knowledge.tk.public.browse", return_value={}), patch("xiaoxue_api.modules.knowledge.tk.public.list_match_trading_tk", return_value={}), patch("xiaoxue_api.modules.team.public.get_match_context", return_value={}), patch.object(service, "list_score_match_results", return_value={}), patch.object(collection, "get_scope_materials", return_value={"result": result}):
        first = REAL_MANIFEST(MATCH)
        result["revision"] = "system-analysis-only-new-revision"
        result["sections"].append({"id": "analysis", "items": [{"text": "系统新解释"}]})
        assert REAL_MANIFEST(MATCH) == first
        result["sections"][0]["items"][0]["conditions"] = "只在边线先动时适用"
        updated = REAL_MANIFEST(MATCH)
        assert updated["internal"] != first["internal"]
        assert {key: value for key, value in updated.items() if key != "internal"} == {key: value for key, value in first.items() if key != "internal"}


def test_shared_author_source_is_readable_even_without_new_match_specific_sources():
    shared = [{"id": "shared_digest", "title": "赛事与双方已准备依据", "selection_status": "screened", "items": [article()]}]
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    with patch.object(repo, "collect_internal", return_value=(shared, [])), patch.object(repo, "collect_library", return_value=([], [])), patch.object(repo, "collect_external", return_value=([], [])), patch.object(repo, "summarize_materials", return_value=([], [])), patch.object(repo, "analyze_materials", return_value=([], [])):
        collection.run_collection(task["id"])
    result = collection.get_prepared_materials(MATCH)["result"]
    assert result["delivery"]["public_author_analysis"] == "available"
    assert result["delivery"]["public_analysis"] == "screened"
    assert result["delivery"]["ready"] is False
    assert "复用" in result["summary"]


def test_cancelled_automatic_match_pauses_without_discarding_readable_result():
    from xiaoxue_api.modules.match.event.preparation import ZONE
    now = datetime.now(ZONE)
    row = {"team_a": "AAA", "team_b": "BBB", "stage": "S16", "date": (now + timedelta(days=1)).date().isoformat(), "time": "18:00"}
    with patch.object(collection, "list_schedules", return_value=[row]):
        task = collection.prepare_upcoming(now_value=now, dispatch=False)["tasks"][0]
    assert task["automatic_schedule"] is True
    worker = repo.claim(task["id"])
    repo.finish(worker, {"match": worker["match"], "updated_at": repo.now(), "status": "partial", "sections": [{"id": "digest", "items": [{"text": "保留原成果"}]}]})
    task = collection.prepare_materials(task["match"], refresh=True, dispatch=False)["task"]
    # Marked automatic work is checked against current schedules before claim.
    repo.update_task(task["id"], {"automatic_schedule": True})
    original = collection.get_collection_task(task["id"])["result"]
    with patch.object(collection, "list_schedules", return_value=[] ) as read, patch.object(collection, "_run_claimed_collection", side_effect=AssertionError("已取消，不得再跑采集")):
        collection.run_collection(task["id"])
    assert read.call_count == 1
    after = collection.get_collection_task(task["id"])
    assert after["task"]["state"] == "paused"
    assert after["result"] == original
    with patch.object(collection, "list_schedules", return_value=[row]):
        restored = collection.prepare_upcoming(now_value=now, dispatch=False)["tasks"][0]
        assert restored["state"] == "queued"
        with patch.object(collection, "_run_claimed_collection") as run:
            collection.run_collection(restored["id"])
        assert run.call_count == 1


def test_unknown_schedule_defers_automatic_work_without_cancelling_or_calling_model():
    task = collection.prepare_materials(MATCH, dispatch=False)["task"]
    repo.update_task(task["id"], {"automatic_schedule": True})
    with patch.object(collection, "list_schedules", side_effect=OSError("temporary local source failure")), patch.object(collection, "_run_claimed_collection", side_effect=AssertionError("未知状态不能继续耗费模型")):
        collection.run_collection(task["id"])
    after = collection.get_collection_task(task["id"])["task"]
    assert after["state"] == "queued" and after["attempts"] == 0
    assert "等待" in after["message"]
    assert after["next_check_at"] > repo.now()
    with patch.object(collection, "list_schedules", side_effect=AssertionError("下次检查前不重复查询")):
        assert collection._claim_current_task(task["id"]) is None


def test_rescheduling_keeps_distinct_identity_and_does_not_pause_manual_research():
    manual = collection.prepare_materials(MATCH, dispatch=False)["task"]
    with patch.object(collection, "list_schedules", side_effect=AssertionError("手工任务不受自动赛程撤销")), patch.object(collection, "_run_claimed_collection") as execute:
        collection.run_collection(manual["id"])
    assert execute.call_count == 1
    now = datetime.fromisoformat("2099-10-20T10:00:00+08:00")
    rows = [{"team_a": "AAA", "team_b": "BBB", "stage": "S16", "date": "2099-10-24", "time": hour} for hour in ("18:00", "20:00")]
    with patch.object(collection, "list_schedules", return_value=rows):
        report = collection.prepare_upcoming(now_value=now, dispatch=False)
    assert len({task["id"] for task in report["tasks"]}) == 2
    assert not repo.read(manual["id"])["task"].get("automatic_schedule")
