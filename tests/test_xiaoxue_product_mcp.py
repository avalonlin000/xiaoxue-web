from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock


def _candidate_path() -> Path:
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
