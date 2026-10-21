import asyncio
import io
import json

import pytest

from scripts.verify_capability_delivery import _agent_tool_readback, _api_projection
from xiaoxue_api.core.module_loader import discover_module_names
from xiaoxue_api.core.module_registry import normalize_manifest
from xiaoxue_api.core.product_modules import load_module_contract
from xiaoxue_api.modules.fundamentals.manifest import MODULE


class _JsonResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def test_fundamentals_delivery_contract_is_complete_and_preserves_agent_autonomy():
    manifest = normalize_manifest(MODULE, module_name="fundamentals")
    delivery = manifest["delivery"]
    assert delivery["source"]["snapshot"] == "ts_stage_snapshots"
    assert delivery["agent_entry"]["tool"] == "xiaoxue_get_team"
    assert "小雪自主决定" in delivery["agent_entry"]["behavior"]
    ts_contract = next(item for item in load_module_contract()["modules"] if item["id"] == "ts_strength")
    assert delivery["projections"] == [
        {
            "endpoint": ts_contract["source_of_truth"]["api"],
            "fields": [
                f"{ts_contract['source_of_truth']['display_path']}.{field}"
                for field in ts_contract["field_mapping"]["display"]
            ],
        }
    ]
    assert delivery["acceptance"] == [
        "snapshot_readback",
        "api_projection",
        "agent_tool_readback",
        "automation_entry",
    ]


def test_every_registered_module_has_an_autonomy_preserving_delivery_contract():
    import importlib

    for module_name in discover_module_names():
        raw = importlib.import_module(f"xiaoxue_api.modules.{module_name}.manifest").MODULE
        delivery = normalize_manifest(raw, module_name=module_name)["delivery"]
        assert delivery["configuration"]
        assert delivery["source"]
        assert delivery["projections"]
        assert delivery["acceptance"]
        assert "小雪自主决定" in delivery["agent_entry"]["behavior"]


def test_api_projection_checks_nested_contract_paths(monkeypatch):
    contract = {
        "projections": [
            {
                "endpoint": "/api/fundamentals/teams",
                "fields": ["ts_display.power_score", "ts_display.status"],
            }
        ]
    }
    payload = {
        "teams": [
            {
                "short_name": "KT",
                "ts_stage": "第三赛段",
                "ts_l1": {"rank": 1},
                "ts_l2": {"strength_score": 99},
                "ts_display": {"power_score": 99, "status": "强·平稳"},
            }
        ]
    }
    response = _JsonResponse(json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr("scripts.verify_capability_delivery.urllib.request.urlopen", lambda *_args, **_kwargs: response)

    assert _api_projection(contract, "http://127.0.0.1:8880") == {
        "endpoint": "/api/fundamentals/teams",
        "teams": 1,
    }


def test_api_projection_still_rejects_missing_nested_contract_paths(monkeypatch):
    contract = {
        "projections": [
            {
                "endpoint": "/api/fundamentals/teams",
                "fields": ["ts_display.power_score", "ts_display.status"],
            }
        ]
    }
    payload = {
        "teams": [
            {
                "short_name": "KT",
                "ts_stage": "第三赛段",
                "ts_l1": {"rank": 1},
                "ts_l2": {"strength_score": 99},
                "ts_display": {"power_score": 99},
            }
        ]
    }
    response = _JsonResponse(json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr("scripts.verify_capability_delivery.urllib.request.urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(AssertionError, match="ts_display.status"):
        _api_projection(contract, "http://127.0.0.1:8880")


def test_agent_tool_readback_rejects_missing_manifest_field(monkeypatch):
    # The product MCP server pins fastmcp + mcp 1.x, which cannot share an
    # interpreter with Hermes' mcp 2.0; skip where the adapter is not importable.
    pytest.importorskip("fastmcp", reason="产品 MCP 运行环境不可用，用 python3 scripts/run_tests.py 跑全量")
    async def fake_get_team(*, team):
        assert team == "KT"
        return json.dumps({
            "team": "KT",
            "ts": {
                "power_score": 80,
                "volatility_score": 70,
                "trend": 60,
                "momentum": 55,
            },
        })

    monkeypatch.setattr(
        "scripts.hermes.xiaoxue_product_mcp.xiaoxue_get_team",
        fake_get_team,
    )
    contract = {
        "agent_entry": {
            "tool": "xiaoxue_get_team",
            "fields": [
                "ts.power_score",
                "ts.volatility_score",
                "ts.trend",
                "ts.momentum",
                "ts.status",
            ],
        }
    }

    with pytest.raises(AssertionError, match="ts.status"):
        asyncio.run(_agent_tool_readback(contract))
