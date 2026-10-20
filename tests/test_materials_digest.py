import json
from unittest.mock import patch

from xiaoxue_api.modules.current_event import collection_repository as repo


MATCH = {"team_a": "KC", "team_b": "MVK", "match_date": "2026-10-19"}
ARTICLE = {"title": "Team announcement", "text": "KC announced its training schedule.", "body": "private/full body must not be sent", "url": "https://example.org/announcement", "verification": "source_text", "published_at": ""}


def test_digest_contains_chinese_readable_result_and_original_source():
    response = json.dumps({"items": [{"text": "KC 公布了训练安排。", "why_relevant": "用于了解这场之前的备战安排，时间仍需核对。", "relevance": "useful_background", "event_key": "kc-training", "source_ids": ["S1"], "evidence_quote": ARTICLE["text"]}]})
    with patch.object(repo, "call_digest_model", return_value=response) as model:
        sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE]}])
    assert not missing
    item = sections[0]["items"][0]
    assert "训练安排" in item["text"]
    assert item["url"] == ARTICLE["url"]
    assert item["verification"] == "ai_summary"
    assert "private/full" not in json.dumps(model.call_args.args)
    assert "待核实" in item["source"]
    assert item["why_relevant"].startswith("用于了解")
    assert sections[0]["selection_status"] == "screened"


def test_digest_rejects_unknown_sources_or_unsourced_claims():
    for ids in ([], ["S999"], ["S1", "S999"]):
        with patch.object(repo, "call_digest_model", return_value=json.dumps({"items": [{"text": "未经来源支持的说法", "source_ids": ids}]})):
            sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE]}])
        assert not sections
        assert missing


def test_digest_failure_keeps_original_materials_and_does_not_retry():
    sections = [{"id": "news", "items": [ARTICLE]}]
    with patch.object(repo, "call_digest_model", side_effect=TimeoutError) as model:
        result, missing = repo.summarize_materials(MATCH, sections)
    assert result == [] and missing
    assert sections[0]["items"][0] == ARTICLE
    assert model.call_count == 1


def test_digest_with_no_external_evidence_does_not_call_model():
    with patch.object(repo, "call_digest_model") as model:
        sections, missing = repo.summarize_materials(MATCH, [{"id": "strength", "items": [{"text": "KC 20"}]}])
    model.assert_not_called()
    assert sections == []


def screened_item(**changes):
    return {"text": "KC 公布了训练安排。", "why_relevant": "用于了解本场备战情况，发布时间仍待核对。",
            "relevance": "useful_background", "event_key": "kc-training", "source_ids": ["S1"],
            "evidence_quote": ARTICLE["text"], **changes}


def test_successful_screening_can_select_nothing_without_becoming_an_error():
    with patch.object(repo, "call_digest_model", return_value='{"items": []}'):
        sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE]}])
    assert missing == []
    assert sections[0]["selection_status"] == "screened"
    assert sections[0]["items"] == []
    assert "未发现" in sections[0]["summary"]


def test_coarse_screen_requires_a_match_reason_not_just_a_translated_paragraph():
    for change in ({"why_relevant": ""}, {"relevance": "incidental_mention"}, {"event_key": ""}):
        with patch.object(repo, "call_digest_model", return_value=json.dumps({"items": [screened_item(**change)]})):
            sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE]}])
        assert sections == [] and missing


def test_undated_and_old_roster_news_cannot_be_promoted_to_current_match_updates():
    for published_at in ("", "2026-01-01", "not-a-date"):
        with patch.object(repo, "call_digest_model", return_value=json.dumps({"items": [screened_item(relevance="match_update")]})):
            sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [{**ARTICLE, "published_at": published_at}]}])
        assert sections == [] and missing


def test_same_event_is_kept_once_even_when_several_sources_repeat_it():
    rows = [screened_item(), screened_item(source_ids=["S2"], text="另一报道也提到 KC 的相同训练安排。")]
    with patch.object(repo, "call_digest_model", return_value=json.dumps({"items": rows})):
        sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE, {**ARTICLE, "url": "https://example.org/repost"}]}])
    assert missing == []
    assert len(sections[0]["items"]) == 1


def test_selected_point_does_not_require_padding_to_a_minimum_word_count():
    with patch.object(repo, "call_digest_model", return_value=json.dumps({"items": [screened_item(text="KC 已更改训练安排。")]})):
        sections, missing = repo.summarize_materials(MATCH, [{"id": "news", "items": [ARTICLE]}])
    assert not missing
    assert sections[0]["items"][0]["text"] == "KC 已更改训练安排。"


def test_future_or_post_start_publications_cannot_be_prematch_updates():
    identity = {**MATCH, "match_time": "2026-10-19 02:00:00"}
    response = json.dumps({"items": [screened_item(relevance="match_update")]})
    for published in ("2026-10-20", "2026-10-19T02:01:00+08:00", "2026-10-19T00:31:00+08:00"):
        with patch.object(repo, "now", return_value="2026-10-19T00:30:00+08:00"), patch.object(repo, "call_digest_model", return_value=response):
            sections, missing = repo.summarize_materials(identity, [{"id": "news", "items": [{**ARTICLE, "published_at": published}]}])
        assert not sections and missing


def test_timestamped_recent_source_before_cutoff_can_be_a_match_update():
    response = json.dumps({"items": [screened_item(relevance="match_update")]})
    with patch.object(repo, "now", return_value="2026-10-19T00:30:00+08:00"), patch.object(repo, "call_digest_model", return_value=response):
        sections, missing = repo.summarize_materials({**MATCH, "match_time": "02:00"}, [{"id": "news", "items": [{**ARTICLE, "published_at": "2026-10-18T18:00:00+08:00"}]}])
    assert sections and not missing
def test_scope_analysis_uses_its_own_existing_method_contract():
    from scripts.summarize_match_materials import select_prompt, PROMPT, DISCUSSION_PROMPT

    selected = select_prompt({"operation": "scope_analysis", "subject": {"scope": "team", "team": "AL"}})
    assert selected != PROMPT
    assert selected != DISCUSSION_PROMPT
    assert '"source_ids"' in selected
    assert "不编造对手" in selected
    assert select_prompt({"operation": "judgment_discussion"}) == DISCUSSION_PROMPT
    assert select_prompt({}) == PROMPT
