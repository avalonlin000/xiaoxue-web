from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest import TestCase

from xiaoxue_api.core.product_modules import (
    REQUIRED_MODULE_FIELDS,
    load_module_contract,
    validate_module_contract,
)


ROOT = Path(__file__).resolve().parents[1]


class ProjectModuleContractTests(TestCase):
    def test_catalog_is_the_single_project_module_registration(self) -> None:
        payload = load_module_contract()
        self.assertEqual(payload["schema"], "xiaoxue-module-contract-v1")
        self.assertEqual(payload["tool_contract"]["mcp"], "xiaoxue-product")
        self.assertFalse(payload["tool_contract"]["structured_output"])
        self.assertEqual(payload["tool_contract"]["model_max_chars"], 3000)
        self.assertEqual(payload["result_contract"]["statuses"][-1], "error")
        modules = payload["modules"]
        self.assertEqual(
            [item["id"] for item in modules],
            [
                "ts_strength",
                "team_profile",
                "tk",
                "current_match",
                "version_lineup",
                "daily_knowledge",
                "knowledge_automation",
                "attention_config",
            ],
        )
        for module in modules:
            self.assertTrue(set(REQUIRED_MODULE_FIELDS) <= set(module))
            self.assertTrue(module["source_of_truth"])
            self.assertTrue(module["user_entry"])
            self.assertTrue(module["agent_entry"])
            self.assertTrue(module["read_capability"])
            self.assertTrue(module["bounded_write_capability"])
            self.assertTrue(module["readback_capability"])
            self.assertTrue(module["consumers"])
            self.assertIn(module["status"], {"available", "partial", "blocked", "deprecated"})

    def test_project_object_catalog_reuses_shared_lifecycle_and_records_gaps(self) -> None:
        project = json.loads((ROOT / "config/project-contract.json").read_text(encoding="utf-8"))
        catalog = project["object_catalog"]
        self.assertEqual(catalog["contract"], "shared-object-package-v1")
        self.assertIn("ordinary_tk", catalog["shared_lifecycle"])
        self.assertIn("trading_tk", catalog["shared_lifecycle"])
        self.assertEqual(set(catalog["objects"]), {"lol", "valorant", "cs2", "football"})
        self.assertTrue(catalog["objects"]["football"]["known_gaps"])

    def test_invalid_catalog_rejects_missing_contract_fields_and_duplicate_ids(self) -> None:
        payload = load_module_contract()
        invalid = json.loads(json.dumps(payload, ensure_ascii=False))
        invalid["modules"][0].pop("readback_capability")
        with self.assertRaisesRegex(ValueError, "readback_capability"):
            validate_module_contract(invalid)

        invalid = json.loads(json.dumps(payload, ensure_ascii=False))
        invalid["modules"][1]["id"] = invalid["modules"][0]["id"]
        with self.assertRaisesRegex(ValueError, "重复"):
            validate_module_contract(invalid)

    def test_frontend_loaders_reference_registered_module_ids_without_copying_contract(self) -> None:
        source = (ROOT / "src/app/module-catalog.js").read_text(encoding="utf-8")
        registered = {
            item["id"] for item in load_module_contract()["modules"]
            if item["compatibility"].get("frontend_loaders")
        }
        referenced: set[str] = set()
        for raw in __import__("re").findall(r"contract_ids:\s*(\[[^\]]+\])", source):
            referenced.update(ast.literal_eval(raw))
        self.assertEqual(referenced, registered)
        self.assertNotIn('source_of_truth:', source)

    def test_formal_docs_and_root_skill_point_to_the_same_model_guide(self) -> None:
        guide = ROOT / "docs/小雪项目总使用说明.md"
        guide_text = guide.read_text(encoding="utf-8")
        self.assertIn("查、记、改、分析和新增", guide_text)
        self.assertIn("缺数据", guide_text)
        self.assertIn("结构级", guide_text)
        product = (ROOT / "docs/交易信息系统-总体设计.md").read_text(encoding="utf-8")
        engineering = (ROOT / "docs/交易信息系统-工程实现.md").read_text(encoding="utf-8")
        skill = Path("/home/ubuntu/.agents/skills/小雪/SKILL.md").read_text(encoding="utf-8")
        for text in (product, engineering, skill):
            self.assertIn("小雪项目总使用说明.md", text)
        self.assertIn("小雪是整个项目的完整业务入口", skill)
        self.assertIn("普通已有对象的小范围记录、修正、补充可以直接处理并读回", skill)

    def test_ts_contract_has_one_display_mapping_used_by_frontend_and_consumers(self) -> None:
        ts = next(item for item in load_module_contract()["modules"] if item["id"] == "ts_strength")
        self.assertEqual(
            list(ts["field_mapping"]["display"]),
            ["power_score", "volatility_score", "trend", "momentum", "status"],
        )
        manifest = (ROOT / "xiaoxue_api/modules/fundamentals/manifest.py").read_text(encoding="utf-8")
        frontend = (ROOT / "src/modules/teams/view.js").read_text(encoding="utf-8")
        for field in ts["field_mapping"]["display"]:
            self.assertIn(field, manifest)
            self.assertIn(field, frontend)
        daily = Path("/home/ubuntu/lol_data/scripts/build_daily_report.py").read_text(encoding="utf-8")
        lineup_handoff = (ROOT / "src/modules/lineup-handoff/service.js").read_text(encoding="utf-8")
        for field in ("power_score", "volatility_score"):
            self.assertIn(field, daily)
        self.assertIn("综合实力、稳定性、趋势、势头和状态", lineup_handoff)
        self.assertNotIn("mu / σ / TS", lineup_handoff)

    def test_profile_contract_names_team_profiles_as_source_not_mirror_presence(self) -> None:
        profile = next(item for item in load_module_contract()["modules"] if item["id"] == "team_profile")
        self.assertIn("统一五项队伍画像", profile["source_of_truth"]["label"])
        service = (ROOT / "xiaoxue_api/modules/profiles/service.py").read_text(encoding="utf-8")
        manifest = (ROOT / "xiaoxue_api/modules/profiles/manifest.py").read_text(encoding="utf-8")
        self.assertIn("canonical", service)
        self.assertIn('source\": \"team_profile\"', service)
        self.assertIn('"mode": "team_profiles_primary"', manifest)
        self.assertIn('"mirror_missing_is_empty": False', manifest)

    def test_runtime_module_endpoint_returns_registration_without_write_side_effect(self) -> None:
        from fastapi.testclient import TestClient
        import main

        with TestClient(main.app) as client:
            response = client.get("/api/modules")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "xiaoxue-module-contract-v1")
        self.assertEqual(len(payload["modules"]), 8)
        self.assertTrue(all(item["read_capability"] for item in payload["modules"]))
        self.assertTrue(all(item["readback_capability"] for item in payload["modules"]))
