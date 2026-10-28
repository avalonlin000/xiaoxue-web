import json
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
