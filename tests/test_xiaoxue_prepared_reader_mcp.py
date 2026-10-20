from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock


candidate = Path(os.environ.get("XIAOXUE_PRODUCT_MCP_CANDIDATE", "").strip() or
                 Path(__file__).resolve().parents[1] / "scripts/hermes/xiaoxue_product_mcp.py")
spec = importlib.util.spec_from_file_location("xiaoxue_prepared_reader_candidate", candidate)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def prepared():
    return {"task": {"id": "a" * 24, "state": "partial", "subject": {"scope": "team", "event": "S16 世界赛", "team": "BLG", "scope_key": "private-key"}},
            "result": {"revision": "read-r1", "summary": "已整理的BLG内容", "sections": [
                {"id": "digest", "selection_status": "screened", "items": [{"title": "作者观点", "text": "关注BLG的边线组织。", "published_at": "", "kind": "author_analysis", "url": "https://dpm.lol/worlds", "verification": "ai_summary"}]},
                {"id": "analysis", "items": [{"text": "这是条件推导，不是你的判断。", "verification": "system_inference"}]},
                {"id": "version", "items": [{"text": "旧版本全文" * 1500}]},
                {"id": "news", "items": [{"text": "网页正文含球员卡14 Oct，不是本文发布日期。"}]}]}}


class PreparedReaderTests(IsolatedAsyncioTestCase):
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
