import json
import copy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "config" / "project-center-content.json"


class ProjectCenterContentCoverageTests(unittest.TestCase):
    def setUp(self):
        self.content = json.loads(CONTENT.read_text(encoding="utf-8"))

    def test_development_book_covers_the_project_not_just_a_card_overview(self):
        self.assertEqual(self.content["schema"], "xiaoxue-project-center-content-v2")
        chapters = {item["id"]: item for item in self.content["book"]["chapters"]}
        self.assertEqual(set(chapters), {
            "what-is-this-project", "three-windows", "flexible-thread", "why-this-design",
            "capability-map", "real-status", "long-term-road", "how-to-improve",
        })
        for chapter in chapters.values():
            self.assertTrue(chapter["paragraphs"])
            self.assertTrue(chapter["module_tree_ids"])
        self.assertTrue(any("不会替你下单" in paragraph for paragraph in chapters["what-is-this-project"]["paragraphs"]))
        self.assertTrue(any("不是必须照着跑的流水线" in paragraph for paragraph in chapters["flexible-thread"]["paragraphs"]))
        self.assertTrue(any("五项画像" in paragraph for paragraph in chapters["why-this-design"]["paragraphs"]))
        self.assertTrue(any("待修改" in paragraph for paragraph in chapters["how-to-improve"]["paragraphs"]))
        self.assertGreaterEqual(len(self.content["book"]["status_guide"]), 6)

    def test_module_tree_covers_every_required_category_and_keeps_human_fields(self):
        tree = self.content["module_tree"]
        self.assertEqual([node["id"] for node in tree], [
            "daily-and-automation", "current-event-prep", "records-and-review", "long-term-understanding",
            "methods-and-judgment", "knowledge-and-data", "workbench-and-project", "chat-capability",
        ])
        expected_names = {
            "队伍、TS 与五项画像", "首发与选手信息", "队伍 TK 与交易 TK",
            "赛事框架、赛程与对局", "赛前资料与单场准备", "首发与信息变化",
            "版本理解与适配", "纯十英雄阵容分析", "交易系统、赛前预案与风险条件", "查询与资料分流",
            "单场复盘",
            "TK 资料库与知识搜索", "B 站、公众号与外部知识导入", "版本、队伍、选手维护与数据质量",
            "日报与当前内容准备", "数据就绪与健康状态", "自动化与暂停边界",
            "搜索、筛选、复制与空态", "项目中心、待修改与待体验", "旧入口归档与兼容边界",
            "怎么自然触发", "会得到什么，什么会读回", "固定边界：不会自动发生什么",
        }
        all_nodes = list(walk_nodes(tree))
        self.assertTrue(expected_names.issubset({node["name"] for node in all_nodes}))
        required = {
            "purpose", "when_to_use", "current_capability", "entry", "ability_ids", "related_modules",
            "boundaries", "next_step", "basket_module_id", "engineering_details",
        }
        for node in all_nodes:
            self.assertTrue(required.issubset(node), node["name"])
            self.assertTrue(node["ability_ids"], node["name"])
            self.assertTrue(node["related_modules"], node["name"])
            self.assertIn("source", node["engineering_details"])
            self.assertIn("verification", node["engineering_details"])

    def test_development_map_is_the_user_facing_variety_hierarchy(self):
        groups = self.content["development_map"]["groups"]
        self.assertEqual([group["id"] for group in groups], ["lol", "football", "cs2", "valorant", "shared"])
        module_ids = []
        for group in groups:
            self.assertTrue(group["modules"])
            for module in group["modules"]:
                module_ids.append(module["id"])
                for key in ("purpose", "now", "gaps", "next_step", "basket_module_id"):
                    self.assertTrue(module[key], f"{group['id']}/{module['id']} missing {key}")
                self.assertIsInstance(module["detail_node_ids"], list)
        self.assertEqual(len(module_ids), len(set(module_ids)))
        self.assertNotIn("八个一级模块", self.content["book"]["chapters"][4]["summary"])

    def test_manual_covers_daily_scenarios_and_keeps_them_routed_by_context(self):
        sections = {item["id"]: item for item in self.content["manual"]["sections"]}
        self.assertEqual(set(sections), {
            "first-time", "teams-and-tk", "current-event", "match-prep", "lineup-and-trading",
            "record-and-review", "review-and-long-term", "knowledge-maintenance", "daily-and-improve", "fixed-boundaries",
        })
        for section in sections.values():
            for key in ("what", "where", "say", "get", "not_for", "module_tree_id"):
                self.assertTrue(section[key], f"{section['title']} missing {key}")
        self.assertIn("十个英雄", sections["lineup-and-trading"]["what"])
        self.assertIn("不自动下单", sections["lineup-and-trading"]["not_for"])
        self.assertIn("读回", sections["record-and-review"]["get"])
        self.assertIn("主动暂停", sections["daily-and-improve"]["get"])
        self.assertIn("不自动交易", sections["fixed-boundaries"]["get"])
        self.assertNotEqual(sections["teams-and-tk"]["module_tree_id"], sections["lineup-and-trading"]["module_tree_id"])

        quick_jump_ids = [item["scenario_id"] for item in self.content["manual"]["quick_jumps"]]
        self.assertEqual(quick_jump_ids, [
            "first-time", "teams-and-tk", "current-event", "match-prep", "lineup-and-trading",
            "record-and-review", "review-and-long-term", "knowledge-maintenance", "daily-and-improve", "fixed-boundaries",
        ])

    def test_all_detail_leaves_have_one_owner_and_variety_specific_details_stay_separate(self):
        nodes = {node["id"]: node for node in walk_nodes(self.content["module_tree"])}
        owners = {}
        for group in self.content["development_map"]["groups"]:
            for module in group["modules"]:
                for ref in module["detail_node_ids"]:
                    for node in walk_nodes([nodes[ref]]):
                        self.assertNotIn(node["id"], owners)
                        owners[node["id"]] = group["id"]
                        for key in ("current_capability", "known_gap", "next_step"):
                            self.assertTrue(node.get(key), f"{node['id']}/{key}")
                        text = " ".join(node[key] for key in ("current_capability", "known_gap", "next_step"))
                        for technical in ("MCP", "镜像文件", "正源", "合同", "/api/"):
                            self.assertNotIn(technical, text, node["id"])
        self.assertTrue({node_id for node_id, node in nodes.items() if not node.get("children")}.issubset(owners))
        for node_id in ("hero-static-data", "team-and-market-tk", "daily-report", "golgg-fact-check", "maintenance-and-quality", "schedule-driven-push", "external-fact-intake"):
            self.assertEqual(owners[node_id], "lol")
        self.assertEqual(owners["football-board"], "football")
        self.assertEqual(owners["tk-library-and-search"], "shared")

    def test_invalid_mapping_cannot_silently_lose_or_duplicate_modules(self):
        from xiaoxue_api.modules.platform.center.service import _validate_content, ProjectCenterError

        for mutation in ("missing", "duplicate", "wrong_variety", "blank", "broken_book"):
            content = copy.deepcopy(self.content)
            groups = content["development_map"]["groups"]
            if mutation == "missing":
                groups[0]["modules"][1]["detail_node_ids"].remove("hero-static-data")
            elif mutation == "duplicate":
                groups[-1]["modules"][0]["detail_node_ids"].append("hero-static-data")
            elif mutation == "wrong_variety":
                groups[1]["object_id"] = "lol"
            elif mutation == "blank":
                groups[0]["modules"][0]["now"] = " "
            else:
                content["book"]["chapters"][0]["module_tree_ids"].append("missing-node")
            with self.subTest(mutation=mutation), self.assertRaises(ProjectCenterError):
                _validate_content(content)

    def test_review_packet_includes_facts_and_rejects_unattributed_model_claims(self):
        from scripts.tasks.xiaoxue_project_center_module_review import build_packet, parse_model_json

        packet = build_packet()
        self.assertEqual(packet["structure_check"], "passed")
        self.assertIn("modules", packet["sources"]["config/module-contract.json"])
        self.assertIn("module_tree", packet["sources"]["config/project-center-content.json"])
        for relative in (
            "docs/business/lol.md",
            "docs/business/football.md",
            "docs/business/cs2.md",
            "docs/business/valorant.md",
        ):
            guide = ROOT / relative
            self.assertTrue(guide.is_file(), relative)
            self.assertEqual(packet["sources"][relative], guide.read_text(encoding="utf-8"))
        valid = {"status": "ok", "findings": [], "checked_at": packet["checked_at"]}
        self.assertEqual(parse_model_json(json.dumps(valid), packet), valid)
        attributed = {
            **valid,
            "status": "review_needed",
            "findings": [{
                "kind": "stale",
                "path": "development_map.groups",
                "claim": "足球玩法说明需要核对",
                "evidence": "足球指导规定默认清单只收录至少一种玩法保留的比赛",
                "source": "docs/business/football.md",
                "action": "人工核对 development_map",
            }],
        }
        self.assertEqual(parse_model_json(json.dumps(attributed), packet), attributed)
        invalid = {**valid, "status": "review_needed", "findings": [{"kind": "stale", "path": "development_map.groups", "claim": "过时", "evidence": "无来源", "source": "invented.md", "action": "改写"}]}
        with self.assertRaises(ValueError):
            parse_model_json(json.dumps(invalid), packet)

    def test_default_content_does_not_leak_implementation_paths_or_retired_primary_routes(self):
        public_content = CONTENT.read_text(encoding="utf-8")
        self.assertNotIn("/api/", public_content)
        self.assertNotIn("trade_records", public_content)
        self.assertNotIn("market_notes", public_content)
        self.assertIn("兼容", public_content)


def walk_nodes(nodes):
    for node in nodes:
        yield node
        yield from walk_nodes(node.get("children", []))


if __name__ == "__main__":
    unittest.main()
