from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock
from zoneinfo import ZoneInfo


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


adapter = _load_candidate()


class XiaoxueProductMCPTests(IsolatedAsyncioTestCase):
    def test_public_tool_surface_is_small_and_product_specific(self) -> None:
        self.assertEqual(
            adapter.PUBLIC_TOOL_FUNCTIONS,
            (
                "xiaoxue_get_today",
                "xiaoxue_find_schedules",
                "xiaoxue_start_match_run",
                "xiaoxue_get_match_run",
                "xiaoxue_get_active_match_trade",
                "xiaoxue_pause_match_trade",
                "xiaoxue_save_match_trade_entry",
                "xiaoxue_update_match_run_fact",
                "xiaoxue_get_score_evidence",
                "xiaoxue_debug_reveal_match_result",
                "xiaoxue_get_match_run_review",
                "xiaoxue_add_stage_candidate",
                "xiaoxue_list_stage_candidates",
                "xiaoxue_update_stage_candidate",
                "xiaoxue_remember_trading_tk",
                "xiaoxue_search_trading_tk",
                "xiaoxue_update_trading_tk",
                "xiaoxue_get_match_workspace",
                "xiaoxue_save_match_workspace",
                "xiaoxue_record_match_change",
                "xiaoxue_get_team",
                "xiaoxue_search_tk",
                "xiaoxue_get_tk_entry",
                "xiaoxue_list_market_notes",
                "xiaoxue_record_team_trading_note",
            ),
        )

    async def test_today_uses_product_api_without_filesystem_search(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"day_state": "ready"})) as request:
            payload = json.loads(await adapter.xiaoxue_get_today("2026-07-30"))

        self.assertEqual(payload["day_state"], "ready")
        request.assert_awaited_once_with("GET", "/daily-content", params={"date": "2026-07-30"})

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
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"activity_status": "active", "focus": "trend"})) as request:
            payload = json.loads(await adapter.xiaoxue_start_match_run(
                "看看 HLE 和 DK 这场", "HLE", "DK", event="LCK", match_date="2026-07-30", match_time="18:00", match_format="BO3",
            ))

        self.assertEqual(payload["activity_status"], "active")
        request.assert_awaited_once_with(
            "POST", "/current-event/match-run/start",
            payload={
                "game": "lol", "team_a": "HLE", "team_b": "DK", "event": "LCK",
                "match_date": "2026-07-30", "match_time": "18:00", "match_format": "BO3", "mode": "live",
            },
        )

    async def test_user_named_module_is_passed_through_the_existing_match_open_tool(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"activity_status": "active", "focus": "lineup"})) as request:
            payload = json.loads(await adapter.xiaoxue_start_match_run(
                "打开 HLE 和 DK，这场先看阵容", "HLE", "DK", match_date="2026-07-30", focus="lineup",
            ))

        self.assertEqual(payload["focus"], "lineup")
        self.assertEqual(request.await_args.kwargs["payload"]["focus"], "lineup")
        self.assertEqual(request.await_args.kwargs["payload"]["mode"], "live")

    async def test_historical_replay_is_an_explicit_debug_mode_only(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"mode": "virtual_pre"})) as request:
            await adapter.xiaoxue_start_match_run(
                "回顾昨天 HLE 和 DK，重跑调试", "HLE", "DK", match_date="2026-07-30", mode="virtual_pre",
            )

        self.assertEqual(request.await_args.kwargs["payload"]["mode"], "virtual_pre")

    async def test_relative_yesterday_overrides_model_supplied_today(self) -> None:
        expected = (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"activity_status": "active"})) as request:
            await adapter.xiaoxue_start_match_run(
                "小雪，看一下昨天 TT 打 JDG", "TT", "JDG", match_date=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            )

        self.assertEqual(request.await_args.kwargs["payload"]["match_date"], expected)

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

    async def test_debug_result_reveal_requires_an_explicit_debug_phrase(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(PermissionError):
                await adapter.xiaoxue_debug_reveal_match_result("继续", "HLE", "DK", match_date="2026-07-30")

        request.assert_not_awaited()

    async def test_debug_result_reveal_uses_the_isolated_replay_endpoint(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"result_unlocked": True})) as request:
            payload = json.loads(await adapter.xiaoxue_debug_reveal_match_result(
                "公布测试赛果", "HLE", "DK", match_date="2026-07-30",
            ))

        self.assertTrue(payload["result_unlocked"])
        request.assert_awaited_once_with(
            "POST", "/current-event/match-run/unlock-result",
            payload={"game": "lol", "team_a": "HLE", "team_b": "DK", "match_date": "2026-07-30"},
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
        self.assertIn("不得自行确认趋势", summary["reply_contract"]["rules"])
        self.assertIn("不强推版本", summary["reply_contract"]["rules"])


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
                "confirmed_by_user": False,
            },
        )

    async def test_trend_entry_requires_an_explicit_user_confirmation_phrase(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(PermissionError):
                await adapter.xiaoxue_save_match_trade_entry(
                    "你看看有什么趋势", "HLE", "DK", "trend", "换人队近期表现好",
                )

        request.assert_not_awaited()

    async def test_user_can_remember_a_rule_as_candidate_without_a_match(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_remember_trading_tk(
                "最近换人的队伍都在赢或者发挥好，帮我记着",
                "最近换人的队伍更容易赢或发挥好",
                "roster",
                "当前版本，后续继续验证",
                "region",
                "LPL",
                "",
                "26.15",
            )

        request.assert_awaited_once_with(
            "POST", "/trading-tk",
            payload={
                "category": "roster",
                "statement": "最近换人的队伍更容易赢或发挥好",
                "context": "当前版本，后续继续验证",
                "scope": "region",
                "region": "LPL",
                "subject": "",
                "version_context": "26.15",
                "source_command": "最近换人的队伍都在赢或者发挥好，帮我记着",
            },
        )

    async def test_stage_candidate_targets_team_instead_of_creating_a_match_note(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            await adapter.xiaoxue_add_stage_candidate(
                "HLE 换人后的主动性值得后面整理", "HLE", "DK", "team", "HLE", "换人影响",
                "换人后中野主动性连续兑现", "可能改变 HLE 当前版本适配判断",
            )

        self.assertEqual(request.await_args.kwargs["payload"]["target_type"], "team")
        self.assertEqual(request.await_args.kwargs["payload"]["target_name"], "HLE")

    async def test_match_workspace_reads_one_product_endpoint(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"exists": True})) as request:
            payload = json.loads(await adapter.xiaoxue_get_match_workspace("AL", "EDG", event="LPL"))

        self.assertTrue(payload["exists"])
        request.assert_awaited_once_with(
            "GET",
            "/current-event/match-workspace",
            params={"team_a": "AL", "team_b": "EDG", "event": "LPL"},
        )

    async def test_match_workspace_write_requires_explicit_save_intent(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(PermissionError):
                await adapter.xiaoxue_save_match_workspace(
                    "这场就这样吧", "AL", "EDG", "A 小分", "前期主动", "等十分钟", "换人则取消",
                )

        request.assert_not_awaited()

    async def test_explicit_match_workspace_write_uses_one_formal_api_call(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"ok": True})) as request:
            payload = json.loads(await adapter.xiaoxue_save_match_workspace(
                "小雪，留存当前判断", "AL", "EDG", "A 小分", "前期主动", "等十分钟", "换人则取消",
                event="LPL", match_date="2026-07-31", match_time="17:00", match_format="BO3",
            ))

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with(
            "PUT",
            "/current-event/match-workspace",
            payload={
                "game": "lol", "team_a": "AL", "team_b": "EDG", "event": "LPL",
                "match_date": "2026-07-31", "match_time": "17:00", "match_format": "BO3",
                "direction": "A 小分", "reasons": "前期主动", "handling": "等十分钟",
                "change_conditions": "换人则取消",
            },
        )

    async def test_tk_search_uses_the_formal_search_endpoint(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value={"results": []})) as request:
            await adapter.xiaoxue_search_tk("纪律性", team="BLG", limit=99)

        request.assert_awaited_once_with("GET", "/tk/search", params={"q": "纪律性", "limit": 20, "team": "BLG"})

    async def test_write_rejects_non_explicit_user_intent_before_api_call(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(PermissionError):
                await adapter.xiaoxue_record_team_trading_note("这条说得不错", "AL", "加里奥皇子慎进场")

        request.assert_not_awaited()

    async def test_explicit_tk_write_is_one_formal_api_call(self) -> None:
        result = {"ok": True, "team": "AL", "boundary": "写入现有队伍 TK/Wiki 正源，不新增交易 TK 实体"}
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock(return_value=result)) as request:
            payload = json.loads(
                await adapter.xiaoxue_record_team_trading_note(
                    "记一下tk：al加里奥皇子慎进场counter双法师",
                    "AL",
                    "加里奥皇子慎进场 counter 双法师",
                )
            )

        self.assertTrue(payload["ok"])
        request.assert_awaited_once_with(
            "POST",
            "/team-trading-notes",
            payload={
                "team": "AL",
                "note": "加里奥皇子慎进场 counter 双法师",
                "title": "",
                "market": "",
                "scenario": "",
                "status": "active",
            },
        )

    async def test_invalid_tk_filename_never_reaches_api(self) -> None:
        with mock.patch.object(adapter, "_api_request", new=mock.AsyncMock()) as request:
            with self.assertRaises(ValueError):
                await adapter.xiaoxue_get_tk_entry("../../secret")

        request.assert_not_awaited()
