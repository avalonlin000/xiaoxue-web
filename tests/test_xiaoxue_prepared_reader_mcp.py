from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

import pytest


candidate = Path(os.environ.get("XIAOXUE_PRODUCT_MCP_CANDIDATE", "").strip() or
                 Path(__file__).resolve().parents[1] / "scripts/hermes/xiaoxue_product_mcp.py")
try:
    spec = importlib.util.spec_from_file_location("xiaoxue_prepared_reader_candidate", candidate)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    import_error = None
except ImportError as exc:  # the server runs in its own venv, not the workbench one
    adapter, import_error = None, exc

pytestmark = pytest.mark.skipif(
    adapter is None,
    reason=f"产品 MCP 运行环境不可用，用 python3 scripts/run_tests.py 跑全量：{import_error}",
)


def prepared():
    return {"task": {"id": "a" * 24, "state": "partial", "subject": {"scope": "team", "event": "S16 世界赛", "team": "BLG", "scope_key": "private-key"}},
            "result": {"revision": "read-r1", "summary": "已整理的BLG内容", "sections": [
                {"id": "digest", "selection_status": "screened", "items": [{"title": "作者观点", "text": "关注BLG的边线组织。", "published_at": "", "kind": "author_analysis", "url": "https://dpm.lol/worlds", "verification": "ai_summary"}]},
                {"id": "analysis", "items": [{"text": "这是条件推导，不是你的判断。", "verification": "system_inference"}]},
                {"id": "version", "items": [{"text": "旧版本全文" * 1500}]},
                {"id": "news", "items": [{"text": "网页正文含球员卡14 Oct，不是本文发布日期。"}]}]}}


class PreparedReaderTests(IsolatedAsyncioTestCase):
    async def test_upcoming_preparation_tool_pages_confirmed_results_without_writing(self):
        payload = {"event": "S16 世界赛", "window_start": "2026-10-21", "window_end": "2026-10-28",
                   "confirmed_total": 8, "prepared": 0, "partial": 8, "not_started": 0,
                   "pending_total": 0, "truncated": False, "next_offset": None,
                   "items": [{"match": {"team_a": "GEN", "team_b": "IG", "date": "2026-10-24", "time": "01:00"},
                              "state": "partial", "reason": "首发未核实", "revision": "sample-r1",
                              "task_id": "a" * 24}]}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)) as api:
            raw = await adapter.xiaoxue_get_upcoming_preparation(offset=4)
        response = json.loads(raw)
        assert len(raw) <= 3000 and response["confirmed_total"] == 8
        assert response["items"][0]["read_with"] == {"tool": "xiaoxue_get_match_materials",
                                                    "task_id": "a" * 24, "expected_revision": "sample-r1"}
        api.assert_awaited_once_with("GET", "/current-event/preparation-coverage", params={"offset": 4, "limit": 4})

    async def test_match_reader_keeps_cross_region_comparison_limit(self):
        payload = {"match": {"team_a": "GEN", "team_b": "IG"}, "quantitative": {
            "available": True, "compare": {"comparable": False, "reason": "跨赛区TS不可直接比较"},
            "team_a": {"team": "GEN", "region": "LCK"}, "team_b": {"team": "IG", "region": "LPL"}}}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            raw = await adapter.xiaoxue_prepare_match("GEN", "IG")
        data = json.loads(raw)
        assert len(raw) <= 3000
        assert data["quantitative"]["comparable"] is False
        assert "跨赛区" in data["quantitative"]["comparison_note"]

    async def test_material_citation_preserves_extracted_knowledge_identity(self):
        item = {"text": "已有知识的有条件解释", "kind": "author_analysis", "source_kind": "knowledge_extract",
                "source": "已有知识提炼整理（未复核原文）", "applicability": "unverified_knowledge_extract"}
        assert adapter._material_source(item)["source_kind"] == "knowledge_extract"

    async def test_match_preparation_surfaces_existing_match_task_without_dumping_full_desk(self):
        materials = prepared()
        materials["task"]["match"] = {"team_a": "GEN", "team_b": "IG"}
        materials["task"].pop("subject")
        payload = {"match": {"team_a": "GEN", "team_b": "IG", "event": "S16全球总决赛"},
                   "prepared_materials": materials, "team_a": {"profile": "旧画像" * 12000},
                   "quantitative": {"available": True, "team_a": {"team": "GEN", "power_score": 65},
                                    "team_b": {"team": "IG", "power_score": 57}}}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)) as api:
            raw = await adapter.xiaoxue_prepare_match("GEN", "IG", match_date="2026-10-24", match_time="01:00")
        data = json.loads(raw)
        assert len(raw) <= 3000
        assert data["prepared_materials"]["task_id"] == "a" * 24
        assert data["prepared_materials"]["read_with"] == {"tool": "xiaoxue_get_match_materials", "task_id": "a" * 24, "expected_revision": "read-r1"}
        assert "旧画像" not in raw and "单场" in data["reading_note"]
        api.assert_awaited_once()

    async def test_full_analysis_pages_preserve_source_links_conditions_and_old_background(self):
        payload = prepared()
        payload["result"]["sections"][1]["items"][0]["evidence"] = [
            {"text": "原作者的具体依据。", "source": "作者甲", "url": "https://example.org/analysis",
             "published_at": "2026-10-20", "conditions": "仅旧版本样本", "counterevidence": "本届尚未验证",
             "kind": "author_analysis", "applicability": "previous_patch", "record_id": "private-audit"},
            {"text": "旧版本认识。", "kind": "version_background", "basis_note": "旧背景，适用性未核实"},
        ]
        offset, pages = 0, []
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            while True:
                raw = await adapter.xiaoxue_get_match_materials(team="BLG", section="analysis", offset=offset)
                assert len(raw) <= 3000
                page = json.loads(raw)
                pages.append(page["text"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
        row = json.loads("".join(pages))["evidence"][0]
        assert row["url"] == "https://example.org/analysis" and row["source"] == "作者甲"
        assert row["conditions"] == "仅旧版本样本" and row["counterevidence"] == "本届尚未验证"
        assert row["applicability"] == "previous_patch"
        assert "旧背景，适用性未核实" in "".join(pages)
        assert "private-audit" not in "".join(pages)

    async def test_team_read_reuses_prepared_materials_with_provenance_not_only_old_profile(self):
        async def response(method, endpoint, *, params=None, **kwargs):
            assert method == "GET"
            if endpoint == "/current-event/scope-materials":
                assert params == {"scope": "team", "team": "BLG"}
                return prepared()
            if endpoint.startswith("/profile-full/"):
                return {"markdown": "旧画像" * 3000}
            if endpoint == "/fundamentals/teams":
                return {"teams": []}
            return {}

        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(side_effect=response)) as api:
            raw = await adapter.xiaoxue_get_team("BLG")
        data = json.loads(raw)
        reading = data["prepared_materials"]
        assert reading["revision"] == "read-r1"
        assert "关注BLG" in json.dumps(reading, ensure_ascii=False)
        assert "条件推导" in json.dumps(reading, ensure_ascii=False)
        assert reading["read_with"] == {"tool": "xiaoxue_get_match_materials", "team": "BLG", "expected_revision": "read-r1"}
        assert "归因" in data["reading_note"] and "旧画像" in data["reading_note"]
        assert data["profile_truncated"] is True and len(raw) <= 3000
        assert all(call.args[0] == "GET" for call in api.await_args_list)

    async def test_prepared_materials_unavailable_does_not_hide_other_team_facts_or_claim_empty(self):
        async def response(method, endpoint, **kwargs):
            if endpoint == "/current-event/scope-materials":
                raise RuntimeError("source temporarily unavailable")
            if endpoint.startswith("/profile-full/"):
                return {"markdown": "队伍定位：已保存画像"}
            return {}

        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(side_effect=response)):
            data = json.loads(await adapter.xiaoxue_get_team("BLG"))
        assert "已保存画像" in data["profile"]
        assert data["prepared_materials"]["state"] == "unavailable"
        assert "读取失败" in data["prepared_materials"]["message"]
        assert "takeaways" not in data["prepared_materials"]

    async def test_compact_takeaways_keep_source_and_causal_limits(self):
        payload = prepared()
        payload["result"]["sections"][0]["items"][0].update(
            conditions="仅为赛前作者观点，不是当前实战原因。", counterevidence="尚无本届过程证据。")
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            data = json.loads(await adapter.xiaoxue_get_match_materials(team="BLG"))
        first = data["takeaways"][0]
        assert first["url"] == "https://dpm.lol/worlds"
        assert first["conditions"] == "仅为赛前作者观点，不是当前实战原因。"
        assert first["counterevidence"] == "尚无本届过程证据。"

    async def test_shared_digest_is_visible_in_compact_reading_not_hidden_as_background(self):
        payload = prepared()
        payload["result"]["sections"][0]["id"] = "shared_digest"
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            raw = await adapter.xiaoxue_get_match_materials(team="BLG")
        data = json.loads(raw)
        shared = next(row for row in data["takeaways"] if row["section"] == "shared_digest")
        assert "关注BLG" in shared["text"]
        assert shared["date_note"] == "发布日期未知"
        assert len(raw) <= 3000

    async def test_team_can_read_prepared_scope_without_knowing_a_task_id(self):
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())) as api:
            raw = await adapter.xiaoxue_get_match_materials(scope="team", event="S16 世界赛", team="BLG")
        api.assert_awaited_once_with("GET", "/current-event/scope-materials", params={"scope": "team", "event": "S16 世界赛", "team": "BLG"})
        data = json.loads(raw)
        assert data["subject"] == {"scope": "team", "event": "S16 世界赛", "team": "BLG"}
        assert "private-key" not in raw and "旧版本全文" not in raw and "球员卡14 Oct" not in raw
        assert "关注BLG" in raw and "条件推导" in raw and len(raw) <= 3000
        assert data["takeaways"][0]["published_at"] == ""
        assert data["takeaways"][0]["date_note"] == "发布日期未知"

    async def test_event_or_team_identity_is_inferred_without_task_lookup_or_collection(self):
        for inputs, params in [({"event": "S16 世界赛"}, {"scope": "event", "event": "S16 世界赛"}),
                               ({"team": "BLG"}, {"scope": "team", "team": "BLG"}),
                               ({"scope": "event"}, {"scope": "event"})]:
            with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())) as api:
                await adapter.xiaoxue_get_match_materials(**inputs)
            api.assert_awaited_once_with("GET", "/current-event/scope-materials", params=params)

    async def test_original_task_id_call_remains_compatible(self):
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())) as api:
            await adapter.xiaoxue_get_match_materials("a" * 24, "digest", 0)
        api.assert_awaited_once_with("GET", "/current-event/collection/" + "a" * 24)

    async def test_ambiguous_or_invalid_identity_is_rejected_before_any_api_request(self):
        inputs = [{}, {"task_id": "a" * 24, "team": "BLG"}, {"task_id": "a" * 24, "scope": "event"},
                  {"task_id": "a" * 24, "event": "S16 世界赛"}, {"scope": "event", "team": "BLG"},
                  {"scope": "team"}, {"scope": "match", "event": "S16 世界赛"}, {"scope": "team", "team": "../BLG"},
                  {"event": "赛" * 201}, {"task_id": "../cache"}]
        for value in inputs:
            with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as api:
                with self.assertRaises(ValueError, msg=str(value)):
                    await adapter.xiaoxue_get_match_materials(**value)
                api.assert_not_awaited()

    async def test_raw_background_is_only_read_on_request_and_is_losslessly_pageable(self):
        offset = 0; pieces = []
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())) as api:
            while True:
                raw = await adapter.xiaoxue_get_match_materials(event="S16 世界赛", team="BLG", section="version", offset=offset)
                assert len(raw) <= 3000
                page = json.loads(raw); pieces.append(page["text"])
                if page["next_offset"] is None:
                    break
                assert page["next_offset"] > offset
                offset = page["next_offset"]
        assert json.loads("".join(pieces))["text"] == "旧版本全文" * 1500
        assert all(call.args == ("GET", "/current-event/scope-materials") for call in api.await_args_list)

    def test_tool_discovery_explains_the_direct_existing_content_path(self):
        tool = next(tool for tool in adapter.mcp._tool_manager.list_tools() if tool.name == "xiaoxue_get_match_materials")
        assert {"task_id", "scope", "event", "team", "section", "offset"}.issubset(tool.parameters["properties"])
        assert "task_id" not in tool.parameters.get("required", [])
        assert "粗筛" in tool.description and "系统解释" in tool.description and "只读" in tool.description
        assert "默认只转述takeaways" in tool.description
        assert "不为补字数主动读version/news" in tool.description
        assert "不从原文其他日期" in tool.description
        assert tool.annotations.readOnlyHint is True and tool.annotations.openWorldHint is False

    async def test_research_reads_late_conditions_without_repeating_collection_or_model_calls(self):
        payload = prepared()
        payload["result"]["sections"][1]["items"] = [{
            "text": "近期样本" * 700, "conditions": "仅适用于目前首发和版本。",
            "counterevidence": "后期反例显示不能一概而论。", "verification": "system_inference",
        }]
        offset, pieces = 0, []
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)) as api:
            while True:
                raw = await adapter.xiaoxue_get_match_materials(
                    team="BLG", section="analysis", offset=offset, expected_revision="read-r1")
                assert len(raw) <= 3000
                page = json.loads(raw)
                assert page["revision"] == "read-r1"
                pieces.append(page["text"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
        result = json.loads("".join(pieces))
        assert result["conditions"] == "仅适用于目前首发和版本。"
        assert result["counterevidence"] == "后期反例显示不能一概而论。"
        assert len(pieces) > 1
        assert all(call.args == ("GET", "/current-event/scope-materials") for call in api.await_args_list)

    async def test_changed_material_revision_returns_no_mixed_body_and_restarts_from_zero(self):
        payload = prepared()
        payload["result"]["revision"] = "r" * 24 + "second"
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            raw = await adapter.xiaoxue_get_match_materials(
                team="BLG", section="version", offset=1400, expected_revision="r" * 24 + "first")
        data = json.loads(raw)
        assert data["revision_changed"] is True
        assert data["expected_revision"] == "r" * 24 + "first"
        assert data["revision"] == "r" * 24 + "second"
        assert data["restart_offset"] == 0 and data["next_offset"] is None
        assert data["text"] == "" and "旧版本全文" not in raw and len(raw) <= 3000

    async def test_changed_judgment_revision_returns_no_mixed_body(self):
        payload = {"revision": "new", "contents": [{"text": "新一版绝不能接到旧正文后"}], "analysis": []}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)) as api:
            raw = await adapter.xiaoxue_open_judgment("version", offset=1400, expected_revision="old")
        data = json.loads(raw)
        assert data["revision_changed"] is True and data["revision"] == "new"
        assert data["restart_offset"] == 0 and data["next_offset"] is None
        assert "新一版绝不能接到旧正文后" not in raw
        api.assert_awaited_once_with("GET", "/current-event/judgment-context", params={"method_id": "version"})

    async def test_material_section_directory_is_also_revision_bound(self):
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())):
            data = json.loads(await adapter.xiaoxue_get_match_materials(
                team="BLG", offset=6, expected_revision="stale"))
        assert data["revision_changed"] is True
        assert "sections" not in data and "takeaways" not in data

    def test_discovery_teaches_full_research_without_requesting_user_pagination(self):
        tools = {tool.name: tool for tool in adapter.mcp._tool_manager.list_tools()}
        for name in ("xiaoxue_get_match_materials", "xiaoxue_open_judgment"):
            assert "expected_revision" in tools[name].parameters["properties"]
            assert "expected_revision" not in tools[name].parameters.get("required", [])
            assert "revision_changed" in tools[name].description
            assert "不让用户" in tools[name].description
            assert "充分" in tools[name].description

    async def test_registered_mcp_call_returns_one_compact_text_without_structured_duplicate(self):
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=prepared())):
            content = await adapter.mcp.call_tool("xiaoxue_get_match_materials", {
                "team": "BLG", "section": "version", "offset": 1400, "expected_revision": "stale",
            })
        assert isinstance(content, list) and len(content) == 1
        assert content[0].type == "text" and len(content[0].text) <= 3000
        assert json.loads(content[0].text)["revision_changed"] is True
