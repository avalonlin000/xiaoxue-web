from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock
from zoneinfo import ZoneInfo

import pytest


def _candidate_path() -> Path:
    configured = os.environ.get("XIAOXUE_PRODUCT_MCP_CANDIDATE", "").strip()
    if configured:
        return Path(configured)
    staged = Path(__file__).resolve().parents[1] / "xiaoxue-product-mcp" / "xiaoxue_product_mcp.py"
    if staged.exists():
        return staged
    return Path(__file__).resolve().parents[1] / "scripts" / "hermes" / "xiaoxue_product_mcp.py"


def _load_candidate():
    spec = importlib.util.spec_from_file_location("xiaoxue_product_mcp_candidate", _candidate_path())
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Xiaoxue product MCP candidate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    adapter = _load_candidate()
    import_error = None
except ImportError as exc:  # the server runs in its own venv, not the workbench one
    adapter, import_error = None, exc

pytestmark = pytest.mark.skipif(
    adapter is None,
    reason=f"产品 MCP 运行环境不可用，用 python3 scripts/run_tests.py 跑全量：{import_error}",
)


class JudgmentEntryMCPTests(IsolatedAsyncioTestCase):
    async def test_judgment_catalogue_uses_the_same_api_and_is_bounded(self):
        payload = {"version": "r1", "methods": [{"id": f"view-{i}", "title": f"理解角度{i}", "purpose": "用途" * 3000, "status": "ready"} for i in range(7)]}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)) as api:
            raw = await adapter.xiaoxue_get_judgment_views()
        api.assert_awaited_once_with("GET", "/trading-methods")
        assert len(raw) <= 3000
        result = json.loads(raw)
        assert result["views"][0]["id"] == "view-0"
        assert result["next_offset"] is not None
        assert "trace" not in result and "effects" not in result

    async def test_judgment_context_content_is_pageable_not_only_a_menu(self):
        text = "这是完整已有版本理解。\x00" * 300
        payload = {"method": {"id": "version", "title": "版本理解"}, "status": "ok", "revision": "r1", "contents": [{"title": "原认识", "text": text, "kind": "version", "recognition": "unknown"}], "analysis": [], "limitations": [], "discussion_available": True}
        collected, offset = "", 0
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            for _ in range(30):
                raw = await adapter.xiaoxue_open_judgment("version", offset=offset)
                assert len(raw) <= 3000
                result = json.loads(raw)
                collected += result["text"]
                if result["next_offset"] is None:
                    break
                assert result["next_offset"] > offset
                offset = result["next_offset"]
        assert text in collected

    async def test_judgment_discussion_has_explicit_model_timeout_and_never_saves(self):
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"answer": "当前仍需核对条件", "references": [{"id": "version-229", "title": "已有版本理解"}], "context_revision": "r1", "saved": False})) as api:
            raw = await adapter.xiaoxue_discuss_judgment("version", "为什么？")
        assert api.await_args.kwargs["timeout_seconds"] >= 100
        assert api.await_args.args == ("POST", "/current-event/judgment-discussion")
        assert json.loads(raw)["saved"] is False

    async def test_prepared_method_interpretation_keeps_its_actual_evidence_readable(self):
        payload = {"status": "ok", "revision": "r1", "contents": [], "analysis": [{"text": "当前是有条件解释。", "evidence": [{"text": "这是真正用到的官方依据。", "kind": "official_background", "url": "https://example.org/notes"}]}]}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=payload)):
            raw = await adapter.xiaoxue_open_judgment("version-understanding")
        assert len(raw) <= 3000
        assert "这是真正用到的官方依据" in raw
        assert "https://example.org/notes" in raw

    async def test_unsaved_long_reply_is_losslessly_pageable_without_another_model_call(self):
        answer = "完整讨论，不自动保存。\x00" * 300
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"answer": answer, "references": [], "saved": False})) as api:
            page = json.loads(await adapter.xiaoxue_discuss_judgment("version", "怎么看"))
            pieces = [page["text"]]
            while page["next_offset"] is not None:
                raw = await adapter.xiaoxue_get_judgment_reply(page["reply_id"], page["next_offset"])
                assert len(raw) <= 3000
                page = json.loads(raw)
                pieces.append(page["text"])
            assert api.await_count == 1
        assert "".join(pieces) == answer
        with mock.patch.object(adapter.time, "monotonic", return_value=adapter.time.monotonic() + 601):
            with self.assertRaises(ValueError):
                await adapter.xiaoxue_get_judgment_reply(page["reply_id"])


class XiaoxueProductMCPTests(IsolatedAsyncioTestCase):
    def test_product_tools_never_use_fixed_phrase_permission_gates(self) -> None:
        source = _candidate_path().read_text(encoding="utf-8")

        self.assertNotIn("_require_phrase(", source)
        self.assertNotIn("_require_explicit_tk_save", source)
        self.assertNotIn("_require_explicit_match_workspace_save", source)
        self.assertNotRegex(source, r"[A-Z_]+_PHRASES\s*=")

    def test_public_tool_surface_is_small_and_product_specific(self) -> None:
        registered = tuple(tool.name for tool in adapter.mcp._tool_manager.list_tools())
        self.assertEqual(adapter.PUBLIC_TOOL_FUNCTIONS, registered)
        self.assertTrue(all(name.startswith("xiaoxue_") for name in registered))
        self.assertTrue({
            "xiaoxue_get_today",
            "xiaoxue_find_schedules",
            "xiaoxue_prepare_match",
            "xiaoxue_start_match_run",
            "xiaoxue_get_team",
            "xiaoxue_get_ts_updates",
            "xiaoxue_search_tk",
            "xiaoxue_remember",
        }.issubset(registered))

    def test_remember_tool_is_labeled_for_explicit_tk_writes(self) -> None:
        source = _candidate_path().read_text(encoding="utf-8")

        self.assertIn("写入钧钧明确指定的 TK", source)
        self.assertIn("仅当钧钧明确提到 TK 或要求写进 TK 时写入", source)

    async def test_external_news_prefers_recent_reports_and_filters_odds_and_stale_results(self) -> None:
        recent = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
        exa_output = f"""Title: Gen.G Remains Adrift, Falls 0-2 to Dplus KIA
URL: https://www.invenglobal.com/articles/19800/gen-g-remains-adrift-falls-0-2-to-dplus-kia
Published: {recent}
Author: Inven Global
Highlights:
Gen.G lost 0-2 to Dplus KIA in the LCK.
---
Title: GEN vs DK prediction and odds
URL: https://polymarket.com/event/gen-vs-dk
Published: {recent}
Author: Polymarket
Highlights:
Markets and odds for the series.
---
Title: Old roster rumor
URL: https://example.com/old-rumor
Published: 2026-06-01T08:00:00.000Z
Author: Example
Highlights:
An outdated rumor.
"""
        with mock.patch.object(adapter, "_run_exa_search", return_value=exa_output):
            payload = json.loads(await adapter.xiaoxue_search_external_news("GEN DK 赛后消息", recency_days=14, limit=5))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["provider"], "agent-reach/exa")
        self.assertEqual([item["title"] for item in payload["results"]], ["Gen.G Remains Adrift, Falls 0-2 to Dplus KIA"])
        self.assertEqual(payload["results"][0]["freshness"], "verified")
        self.assertNotIn("polymarket", json.dumps(payload, ensure_ascii=False).lower())
        self.assertNotIn("old-rumor", json.dumps(payload, ensure_ascii=False).lower())

    async def test_external_news_marks_tavily_fallback_as_unverified_freshness(self) -> None:
        tavily_output = {
            "success": True,
            "data": {
                "web": [
                    {"title": "LCK official series update", "url": "https://lolesports.com/news/lck-update", "content": "Official update."},
                    {"title": "DK odds prediction", "url": "https://example.com/odds", "content": "Prediction."},
                ]
            },
        }
        with mock.patch.object(adapter, "_run_exa_search", side_effect=RuntimeError("Exa unavailable")), \
             mock.patch.object(adapter, "_run_tavily_search", return_value=tavily_output):
            payload = json.loads(await adapter.xiaoxue_search_external_news("DK 最新消息", recency_days=7, limit=5))

        self.assertEqual(payload["status"], "fallback")
        self.assertEqual(payload["provider"], "hermes/tavily")
        self.assertEqual([item["title"] for item in payload["results"]], ["LCK official series update"])
        self.assertEqual(payload["results"][0]["freshness"], "unverified")

    async def test_collection_is_named_and_passes_only_match_identity(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"task": {"id": "a" * 24, "state": "queued"}})) as request:
            payload = json.loads(await adapter.xiaoxue_collect_match_materials("KC", "MVK", match_date="2026-10-19", match_time="02:00"))
        self.assertEqual(payload["state"], "queued")
        self.assertEqual(request.await_args.args, ("POST", "/current-event/collection"))
        self.assertFalse(request.await_args.kwargs["payload"]["refresh"])

    def test_material_pages_are_bounded_and_losslessly_readable(self) -> None:
        body = "比赛资料\n\\\"\u0001" * 2000
        sections = [{"id": f"part-{index}", "title": "长标题" * 40, "items": [{"text": body}]} for index in range(20)]
        packet = {"task": {"id": "a" * 24, "state": "partial", "message": "正在整理"}, "result": {"match": {"team_a": "KC", "team_b": "MVK", "event": "Worlds"}, "sections": sections, "limitations": ["待核对" * 200] * 10}}
        summary = adapter._material_summary(packet)
        self.assertLessEqual(len(adapter._json(summary)), 3000)
        self.assertEqual(summary["sections_total"], 20)
        self.assertIsNotNone(summary["next_section_offset"])
        offset, pages = 0, []
        while True:
            page = adapter._material_summary(packet, section="part-0", offset=offset)
            self.assertLessEqual(len(adapter._json(page)), 3000)
            pages.append(page["text"])
            if page["next_offset"] is None:
                break
            self.assertGreater(page["next_offset"], offset)
            offset = page["next_offset"]
        self.assertEqual(json.loads("".join(pages))["text"], body)

    def test_material_summary_delivers_both_lines_not_just_progress(self) -> None:
        sections = [
            {"id": "digest", "title": "本场值得知道", "selection_status": "screened", "items": [{"text": "公开消息：本场换人影响中野配合。", "verification": "ai_summary"}]},
            {"id": "analysis", "title": "按我的方法看本场", "items": [{"text": "自身推导：先确认阵容与版本适配。", "verification": "system_inference"}]},
            {"id": "comparison", "title": "两边怎么看", "items": [{"text": "两边对前期节奏的判断相符。", "verification": "system_inference"}]},
        ]
        packet = {"task": {"id": "a" * 24, "state": "partial"}, "result": {"summary": "已准备", "sections": sections}}
        summary = adapter._material_summary(packet)
        rendered = adapter._json(summary)
        self.assertLessEqual(len(rendered), 3000)
        self.assertIn("公开消息：本场换人影响中野配合。", rendered)
        self.assertIn("自身推导：先确认阵容与版本适配。", rendered)
        self.assertIn("两边对前期节奏的判断相符。", rendered)
        self.assertIn("未确认采用", rendered)

    def test_material_pages_hide_storage_paths_and_raw_evidence(self) -> None:
        packet = {"task": {"id": "a" * 24, "state": "completed", "message": "/home/private/task.json"}, "result": {"sections": [{
            "id": "analysis", "items": [{"text": "可读取的本场结论", "verification": "system_inference", "source": "既有方法", "input_evidence": [{"text": "/home/private/profile.md"}], "evidence": [{"text": "已有画像的有效依据"}, {"text": '{"mu":28,"internal_id":"I1"}'}], "path": "/home/private/model.json"}],
        }]}}
        page = adapter._material_summary(packet, section="analysis")
        rendered = adapter._json(page)
        self.assertIn("可读取的本场结论", rendered)
        self.assertIn("已有画像的有效依据", rendered)
        self.assertNotIn("/home/", rendered)
        self.assertNotIn("input_evidence", rendered)
        self.assertNotIn("internal_id", rendered)
        self.assertLessEqual(len(rendered), 3000)

    def test_personal_analysis_projection_removes_reference_ids_not_team_or_patch_names(self) -> None:
        text = "依据：I1要求先看下路；I3、P2和M7把赢法与版本结合。T1的BO5样本与26.16版本仍需核对。"
        packet = {"task": {}, "result": {"sections": [{"id": "analysis", "title": "按我的方法看本场", "items": [{"text": text, "verification": "system_inference"}]}]}}
        for value in (adapter._material_summary(packet), adapter._material_summary(packet, section="analysis")):
            rendered = adapter._json(value)
            self.assertNotRegex(rendered, r"\b(?:I1|I3|P2|M7)\b")
            self.assertIn("要求先看下路", rendered)
            self.assertIn("把赢法与版本结合", rendered)
            self.assertIn("T1的BO5样本与26.16版本", rendered)

    async def test_today_uses_product_api_without_filesystem_search(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"day_state": "ready"})) as request:
            payload = json.loads(await adapter.xiaoxue_get_today("2026-07-30"))

        self.assertEqual(payload["day_state"], "ready")
        request.assert_awaited_once_with("GET", "/daily-content", params={"date": "2026-07-30"})

    async def test_today_projects_report_and_pages_matches_without_paths(self) -> None:
        data = {"date": "2026-10-19", "day_state": "ready", "report": {"url": "https://example.org/report", "publication_status": "verified", "snapshot_at": "2026-10-19T07:00:00+08:00"}, "matches": [{"team_a": "KC", "team_b": "MVK", "stage": "Worlds", "date": "2026-10-19", "time": "02:00"}] * 40, "items": [{"path": "/home/private/report", "summary": "不应透传整份产物" * 1000}]}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=data)):
            raw = await adapter.xiaoxue_get_today("2026-10-19")
        self.assertLessEqual(len(raw), 3000)
        self.assertNotIn("/home/", raw)
        projected = json.loads(raw)
        self.assertEqual(projected["report"]["url"], "https://example.org/report")
        self.assertEqual(projected["matches_total"], 40)
        self.assertIsNotNone(projected["next_offset"])

    async def test_change_basket_has_a_named_compact_read_entry(self) -> None:
        response = {
            "data": {
                "items": [{
                    "module_name": "当前赛事与单场", "optional_note": "我想更快看到下一步", "status": "pending", "is_focus": True,
                    "context_snapshot": {"purpose": "围绕一场比赛整理当前资料", "runtime": {"label": "使用中"}},
                }],
            },
        }
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=response)) as request:
            payload = json.loads(await adapter.xiaoxue_get_change_basket(limit=8))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["current_focus"]["module"], "当前赛事与单场")
        self.assertNotIn("module_id", json.dumps(payload, ensure_ascii=False))
        request.assert_awaited_once_with(
            "GET", "/project-center/change-basket", params={"status": "active", "limit": 8},
        )

    async def test_generic_readonly_api_accepts_direct_fastapi_prefix(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            payload = json.loads(await adapter.xiaoxue_query_readonly_api("/api/health"))

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with("GET", "/health", params={})

    async def test_generic_readonly_api_keeps_product_relative_path(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_query_readonly_api("/health")

        request.assert_awaited_once_with("GET", "/health", params={})

    async def test_generic_mutation_normalizes_direct_fastapi_prefix(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_mutate_safe_api("POST", "/api/example", {"key": "value"})

        request.assert_awaited_once_with("POST", "/example", payload={"key": "value"})

    async def test_data_refresh_has_a_named_xiaoxue_entry(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True, "stages": []})) as request:
            payload = json.loads(await adapter.xiaoxue_refresh_results_and_ts())

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with("POST", "/data-refresh", payload={}, timeout_seconds=900.0)

    async def test_ts_updates_uses_the_named_readonly_history_endpoint(self) -> None:
        response = {
            "team": "KT",
            "days": 30,
            "updates": [{
                "updated_at": "2026-08-15T10:00:00",
                "field": "trend",
                "old_value": "35",
                "new_value": "60",
                "trigger_source": "daily_pipeline",
            }],
        }
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=response)) as request:
            payload = json.loads(await adapter.xiaoxue_get_ts_updates("KT", limit=20, days=30))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["updates"][0]["field"], "trend")
        request.assert_awaited_once_with(
            "GET", "/ts-updates/KT", params={"limit": 20, "days": 30},
        )

    async def test_match_preparation_uses_one_read_only_product_endpoint(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"match": {"team_a": "AL", "team_b": "EDG"}})) as request:
            payload = json.loads(await adapter.xiaoxue_prepare_match(
                "AL", "EDG", event="LPL 第三赛段", match_date="2026-07-30", match_time="17:00", match_format="BO3",
            ))

        self.assertEqual(payload["match"]["team_a"], "AL")
        request.assert_awaited_once_with(
            "GET",
            "/current-event/match-desk",
            params={
                "team_a": "AL", "team_b": "EDG", "event": "LPL 第三赛段",
                "match_date": "2026-07-30", "match_time": "17:00", "match_format": "BO3",
            },
        )

    async def test_normal_match_opens_as_a_resumable_live_trade_thread(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(side_effect=[
            {"activity_status": "active", "focus": "trend"},
            {"boundary": "aggregated"},
        ])) as request:
            payload = json.loads(await adapter.xiaoxue_start_match_run(
                "看看 HLE 和 DK 这场", "HLE", "DK", event="LCK", match_date="2026-07-30", match_time="18:00", match_format="BO3",
            ))

        self.assertEqual(payload["activity_status"], "active")
        self.assertEqual(payload["first_turn_brief"]["boundary"], "aggregated")
        self.assertEqual(request.await_count, 2)
        self.assertEqual(request.await_args_list[0].args, ("POST", "/current-event/match-run/start"))
        self.assertEqual(request.await_args_list[1].args, ("GET", "/research/match-brief"))

    async def test_concrete_match_example_opens_without_a_fixed_start_phrase(self) -> None:
        expected_date = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=2)).isoformat()
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(side_effect=[
            {"activity_status": "active"}, {"match": {"team_a": "HLE", "team_b": "GEN"}},
        ])) as request:
            payload = json.loads(await adapter.xiaoxue_start_match_run(
                "比如后天 HLE 打 GEN", "HLE", "GEN", event="LCK", match_date=expected_date,
            ))

        self.assertEqual(payload["activity_status"], "active")
        self.assertEqual(request.await_count, 2)
        self.assertEqual(request.await_args_list[0].kwargs["payload"], {
            "game": "lol", "team_a": "HLE", "team_b": "GEN", "event": "LCK",
            "match_date": expected_date, "mode": "live",
        })
        self.assertEqual(request.await_args_list[1].kwargs["params"]["match_date"], expected_date)

    async def test_user_named_module_is_passed_through_the_existing_match_open_tool(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"activity_status": "active", "focus": "lineup"})) as request:
            payload = json.loads(await adapter.xiaoxue_start_match_run(
                "打开 HLE 和 DK，这场先看阵容", "HLE", "DK", match_date="2026-07-30", focus="lineup",
            ))

        self.assertEqual(payload["focus"], "lineup")
        self.assertEqual(request.await_args_list[0].kwargs["payload"]["focus"], "lineup")
        self.assertEqual(request.await_args_list[0].kwargs["payload"]["mode"], "live")

    async def test_historical_replay_is_an_explicit_debug_mode_only(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"mode": "virtual_pre"})) as request:
            await adapter.xiaoxue_start_match_run(
                "回顾昨天 HLE 和 DK，重跑调试", "HLE", "DK", match_date="2026-07-30", mode="virtual_pre",
            )

        self.assertEqual(request.await_args_list[0].kwargs["payload"]["mode"], "virtual_pre")

    async def test_relative_yesterday_overrides_model_supplied_today(self) -> None:
        expected = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"activity_status": "active"})) as request:
            await adapter.xiaoxue_start_match_run(
                "小雪，看一下昨天 TT 打 JDG", "TT", "JDG", match_date=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            )

        self.assertEqual(request.await_args_list[0].kwargs["payload"]["match_date"], expected)

    def test_explicit_date_in_command_wins_over_relative_or_supplied_date(self) -> None:
        self.assertEqual(
            adapter._resolve_command_match_date("回顾 2026-07-20 这场", "2026-07-31"),
            "2026-07-20",
        )

    async def test_score_evidence_is_named_and_read_only(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"view": "pre", "score_match": {}})) as request:
            payload = json.loads(await adapter.xiaoxue_get_score_evidence("HLE", "DK", match_date="2026-07-30"))

        self.assertEqual(payload["view"], "pre")
        request.assert_awaited_once_with(
            "GET", "/current-event/score-evidence",
            params={"team_a": "HLE", "team_b": "DK", "match_date": "2026-07-30", "view": "pre"},
        )


    def test_first_turn_run_summary_keeps_a_neutral_draft_without_forcing_version(self) -> None:
        summary = adapter._first_turn_run_summary({
            "exists": True, "activity_status": "active", "focus": "overview",
            "match": {"team_a": "NIP", "team_b": "WBG"}, "facts": [
                {"id": 1, "label": "赛程", "status": "active", "source": "scoregg_schedule"},
                {"id": 2, "label": "NIP 近况", "status": "active", "source": "scoregg_form"},
                {"id": 5, "label": "WBG 近况", "status": "active", "source": "scoregg_form"},
                {"id": 3, "label": "首发", "status": "needs_review", "source": "team_profile"},
                {"id": 4, "label": "没有交易备注", "status": "missing", "source": "trading_note"},
            ],
        })

        self.assertEqual([item["label"] for item in summary["facts"]], ["赛程"])
        self.assertNotIn("all_fact_codes", summary)
        self.assertNotIn("id", summary)
        self.assertEqual(summary["reply_contract"]["start"], "当前：NIP vs WBG｜正在看：单场底稿")
        self.assertEqual(summary["reply_contract"]["shape"], "结论地图 + 完整分区")
        self.assertTrue(any("自行取舍" in rule for rule in summary["reply_contract"]["rules"]))
        self.assertTrue(any("优先使用已聚合信息" in rule for rule in summary["reply_contract"]["rules"]))
        self.assertTrue(any("直接联网搜索" in rule for rule in summary["reply_contract"]["rules"]))


    async def test_one_trade_section_can_be_saved_without_advancing_a_flow(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"focus": "entry"})) as request:
            payload = json.loads(await adapter.xiaoxue_save_match_trade_entry(
                "这场只先记入场条件", "HLE", "DK", "entry", "首发不变且盘口回落时才考虑",
            ))

        self.assertEqual(payload["focus"], "entry")
        request.assert_awaited_once_with(
            "PUT", "/current-event/match-run/entry",
            payload={
                "game": "lol", "team_a": "HLE", "team_b": "DK",
                "section": "entry", "content": "首发不变且盘口回落时才考虑",
            },
        )

    async def test_trend_entry_is_saved_without_a_confirmation_flag(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"focus": "trend"})) as request:
            payload = json.loads(await adapter.xiaoxue_save_match_trade_entry(
                "这个规律我认可，本场就按它留下", "HLE", "DK", "trend", "换人队近期表现好",
            ))

        self.assertEqual(payload["focus"], "trend")
        self.assertNotIn("confirmed_by_user", request.await_args.kwargs["payload"])

    async def test_explicit_tk_write_preserves_raw_text_without_inferred_status(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_remember("写进 TK：最近换人的队伍都在赢或者发挥好")

        request.assert_awaited_once_with(
            "POST", "/tk/remember",
            payload={"text": "写进 TK：最近换人的队伍都在赢或者发挥好", "tags": []},
        )

    async def test_stage_candidate_targets_team_instead_of_creating_a_match_note(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_add_stage_candidate(
                "HLE 换人后的主动性值得后面整理", "HLE", "DK", "team", "HLE", "换人影响",
                "换人后中野主动性连续兑现", "可能改变 HLE 当前版本适配判断",
            )

        self.assertEqual(request.await_args.kwargs["payload"]["target_type"], "team")
        self.assertEqual(request.await_args.kwargs["payload"]["target_name"], "HLE")

    async def test_tk_search_uses_the_formal_search_endpoint(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"results": []})) as request:
            payload = json.loads(await adapter.xiaoxue_search_tk("纪律性", team="BLG", limit=99))

        request.assert_awaited_once_with("GET", "/tk/search", params={"q": "纪律性", "limit": 20, "team": "BLG"})
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["effects"], {"effect": "read", "network": False, "writes": []})
        self.assertEqual(payload["trace"]["capability"], "tk_knowledge")

    async def test_get_team_uses_one_team_query_and_returns_only_display_ts(self) -> None:
        async def response(method, endpoint, *, params=None, **kwargs):
            if endpoint.startswith("/profile-full/"):
                return {"markdown": "# HLE 队伍画像\n- 队伍定位：测试队伍"}
            if endpoint.startswith("/version-understanding/"):
                return {"tk_items": [{"title": "知识标题" * 40} for _ in range(20)]}
            if endpoint.startswith("/team-trading-notes/"):
                return {"notes": [{"title": "交易标题" * 40} for _ in range(20)]}
            if endpoint == "/fundamentals/teams":
                self.assertEqual(params["team"], "HLE")
                self.assertEqual(params["limit"], 1)
                self.assertNotEqual(params["limit"], 80)
                return {"teams": [{
                    "short_name": "HLE",
                    "ts_display": {
                        "power_score": 80, "volatility_score": 70, "trend": 60,
                        "momentum": 55, "status": "强·上升",
                    },
                    "ts_l2": {"mu": 30, "sigma": 4, "ts": 18, "matches": 10, "wins": 7},
                }]}
            raise AssertionError(endpoint)

        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(side_effect=response)):
            encoded = await adapter.xiaoxue_get_team("HLE", trading_note_limit=20)
        self.assertLessEqual(len(encoded), 3000)
        payload = json.loads(encoded)
        self.assertEqual(set(payload["ts"]), {"power_score", "volatility_score", "trend", "momentum", "status"})
        self.assertNotIn("mu", encoded)
        self.assertNotIn("sigma", encoded)
        self.assertNotIn("ts_l2", encoded)

    async def test_migrated_read_tools_use_the_common_result_envelope(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=[])):
            payload = json.loads(await adapter.xiaoxue_find_schedules(team="HLE", limit=3))

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(
            set(payload),
            {"status", "summary", "data", "sources", "effects", "readback", "gaps", "conflicts", "error", "trace"},
        )
        self.assertEqual(payload["data"], [])
        self.assertEqual(payload["trace"], {"capability": "team_data", "version": "1.0.0"})

    async def test_explicit_tk_write_uses_only_raw_text(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True, "source": "钧钧口述"})) as request:
            payload = json.loads(await adapter.xiaoxue_remember("记到 TK：这场先不碰，观察前十五分钟。"))

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with(
            "POST", "/tk/remember", payload={"text": "记到 TK：这场先不碰，观察前十五分钟。", "tags": []},
        )

    async def test_explicit_tk_write_preserves_user_wording(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            payload = json.loads(await adapter.xiaoxue_remember("写进 TK：以后 AL 遇到双法师要想到这套反制"))

        self.assertTrue(payload["ok"])
        request.assert_awaited_once()

    async def test_explicit_tk_write_is_one_formal_api_call(self) -> None:
        result = {"ok": True, "team": "AL"}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=result)) as request:
            payload = json.loads(
                await adapter.xiaoxue_remember(
                    "记一下tk：al加里奥皇子慎进场counter双法师", trading=True,
                )
            )

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with(
            "POST",
            "/trading-tk",
            payload={
                "statement": "记一下tk：al加里奥皇子慎进场counter双法师",
                "source_command": "xiaoxue_remember(trading=true)",
                "category": "general",
                "scope": "global",
            },
        )

    async def test_invalid_tk_filename_never_reaches_api(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(ValueError):
                await adapter.xiaoxue_get_tk_entry("../../secret")

        request.assert_not_awaited()

    async def test_update_team_profile_sends_only_the_named_section(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"team_name": "GEN", "bp_tendency": "前期主动"})) as request:
            payload = json.loads(await adapter.xiaoxue_update_team_profile(
                "把 GEN 的 BP 倾向改成更重前期主动", "GEN", bp_tendency="前期主动",
            ))
        self.assertEqual(payload["team_name"], "GEN")
        request.assert_awaited_once_with("PUT", "/team-profile/GEN", payload={"bp_tendency": "前期主动"})
