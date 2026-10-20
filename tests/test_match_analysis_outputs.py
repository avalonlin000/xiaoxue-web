import json
from unittest.mock import patch
import pytest

from xiaoxue_api.modules.current_event import collection_repository as repo


MATCH = {"team_a": "AAA", "team_b": "BBB", "event": "LPL", "match_date": "2099-10-20", "match_time": "18:00"}


@pytest.fixture(autouse=True)
def isolate_collection_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "materials"))
    monkeypatch.setattr("xiaoxue_api.modules.current_event.service.get_current_event", lambda: {"event": "unit-test"})
    for name in ("search", "read_article", "call_digest_model"):
        monkeypatch.setattr(repo, name, lambda *args, **kwargs: pytest.fail("单测禁止真实网络或模型请求"))


def test_analysis_articles_are_not_rejected_for_containing_prediction():
    lead = {"url": "https://example.org/aaa-bbb-prediction", "title": "AAA BBB tactical prediction", "published_at": ""}
    body = "AAA faces BBB in the upcoming match. " * 5 + "\n" + "The reason is the way they give up side waves before grouping. " * 7
    with patch.object(repo, "search", return_value=([lead], "")), patch.object(repo, "read_article", return_value=body):
        rows, _ = repo.collect_external(MATCH)
    assert rows
    assert "give up side waves" in rows[0]["text"]
    assert rows[0]["source_id"] and rows[0]["content_hash"]


def test_methods_execute_with_canonical_instructions_and_input_references():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    evidence = [{"id": "I1", "text": "AAA 的正式画像：依靠边线牵制后转资源团。", "kind": "team_profile"}]
    response = {"items": [{"method_id": "trading", "text": "主要矛盾是边线牵制能否转成资源先手。", "basis": "已有画像支持这条赢法。", "confirmation": "边线压力持续迫使对手先回防。", "invalidation": "边线压力无法维持，转线先手丢失。", "source_ids": ["I1"]}], "comparison": []}
    with patch.object(analysis, "collect_inputs", return_value=evidence), patch.object(repo, "call_digest_model", return_value=json.dumps(response)) as model:
        sections, missing = analysis.analyze(MATCH, [])
    assert not missing
    packet = model.call_args.args[0]
    assert packet["operation"] == "match_analysis"
    assert packet["inference_scope"] == "supported"
    assert "主要矛盾" in next(m["instruction"] for m in packet["methods"] if m["id"] == "trading")
    item = sections[0]["items"][0]
    assert item["method_version"] and item["input_revision"]
    assert item["verification"] == "system_inference"
    assert "失效" in item["text"] and item["source_ids"] == ["I1"]


def test_unknown_evidence_and_method_cannot_be_saved_as_personal_analysis():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    for method, refs in [("invented", ["I1"]), ("trading", ["missing"])]:
        response = {"items": [{"method_id": method, "text": "猜测", "basis": "猜测", "confirmation": "猜测", "invalidation": "猜测", "source_ids": refs}]}
        with patch.object(analysis, "collect_inputs", return_value=[{"id": "I1", "text": "已确认队伍资料", "kind": "team_profile"}]), patch.object(repo, "call_digest_model", return_value=json.dumps(response)):
            sections, missing = analysis.analyze(MATCH, [])
        assert not sections and missing


def test_cross_region_scores_do_not_enable_cycle_method():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    evidence = [{"id": "I1", "kind": "cycle", "text": "双方跨赛区", "comparable": False}]
    with patch.object(analysis, "collect_inputs", return_value=evidence), patch.object(repo, "call_digest_model") as model:
        sections, missing = analysis.analyze(MATCH, [])
    model.assert_not_called()
    assert not sections and missing


def test_no_source_evidence_never_calls_the_analysis_model():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    with patch.object(analysis, "collect_inputs", return_value=[]), patch.object(repo, "call_digest_model") as model:
        sections, missing = analysis.analyze(MATCH, [])
    model.assert_not_called()
    assert not sections and missing


def test_unverified_profile_is_background_not_supported_current_team_fact():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    from xiaoxue_api.modules.fundamentals import public as fundamentals
    from xiaoxue_api.modules.version_understanding import public as version
    sections = [{"id": "team_AAA", "items": [{"source": "已有队伍画像", "text": "旧国内赛赢法", "updated_at": "2026-01-01"}]}]
    with patch.object(fundamentals, "get_match_context", return_value={}), patch.object(version, "get_global_version_understanding", return_value={}):
        inputs = analysis.collect_inputs(MATCH, sections)
    assert inputs[0]["kind"] == "team_profile_background"
    with patch.object(analysis, "collect_inputs", return_value=inputs), patch.object(repo, "call_digest_model") as model:
        result, _ = analysis.analyze(MATCH, [])
    assert not result
    model.assert_not_called()


def test_library_pages_past_trading_notes_before_limiting_analysis():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    from xiaoxue_api.modules.tk_knowledge import public

    def page(**kwargs):
        offset = kwargs.get("offset", 0)
        rows = ([{"filename": f"trade-{i}", "type": "trading_tk"} for i in range(30)]
                if offset == 0 else [{"filename": "article", "type": "knowledge_tk"}])
        return {"results": rows, "has_more": offset == 0}

    with patch.object(public, "browse", side_effect=page), patch.object(public, "get_entry", return_value={"content": "已有分析正文。" * 30}):
        sections, _ = analysis.collect_library(MATCH)
    assert len(sections[0]["items"]) == 1


def test_cycle_collection_requires_a_nonempty_status():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    from xiaoxue_api.modules.fundamentals import public as fundamentals
    from xiaoxue_api.modules.version_understanding import public as version
    from xiaoxue_api.modules.current_event import service
    side = {"region": "LPL", "power_score": 10, "volatility_score": 2, "trend": "up", "momentum": 1}
    for status in (None, "", "   "):
        context = {"team_a": {**side, "team": "AAA", "status": status}, "team_b": {**side, "team": "BBB", "status": status}}
        with patch.object(fundamentals, "get_match_context", return_value=context), patch.object(version, "get_global_version_understanding", return_value={}), patch.object(service, "list_score_match_results", return_value={"results": [{}, {}]}):
            inputs = analysis.collect_inputs(MATCH, [])
        assert not any(row["kind"] == "cycle" for row in inputs)


def test_format_and_version_numbers_are_not_invented_trading_thresholds():
    from xiaoxue_api.modules.current_event import analysis_repository as analysis
    for condition, accepted in (("若本场BO5持续围绕下路形成压力。", True), ("若本场确认采用26.16再核对适用性。", True), ("若经济领先达到3000才确认。", False), ("若比赛进入15分钟。", False)):
        response = {"items": [{"method_id": "trading", "text": "条件分析，尚不能判断方向。", "basis": "只引用已有待核对规律。", "confirmation": condition, "invalidation": "实际表现不符合该规律。", "source_ids": ["I1"]}]}
        with patch.object(analysis, "collect_inputs", return_value=[{"id": "I1", "text": "已有条件规律", "kind": "candidate_rule"}]), patch.object(repo, "call_digest_model", return_value=json.dumps(response)):
            sections, _ = analysis.analyze(MATCH, [])
        assert bool(sections) == accepted
        if accepted:
            assert sections[0]["items"][0]["inference_scope"] == "conditional"
