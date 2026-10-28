"""小雪菜单 = 项目中心内容正源（唯一来源）。

约定：小雪 Skill 的「引导与菜单」不另存功能清单，只读
`config/project-center-content.json` 的 manual（或 scripts/xiaoxue_menu.py 的输出）。
这份测试守住这条契约：内容里有的场景和常用说法，菜单一定能给出来；菜单输出里
不出现文件路径、接口或内部字段。
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "config" / "project-center-content.json"
MENU_SCRIPT = ROOT / "scripts" / "xiaoxue_menu.py"
SKILL = Path("/home/ubuntu/.agents/skills/小雪/SKILL.md")
GUIDE = ROOT / "AGENTS.md"


def run_menu(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(MENU_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class MenuSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.content = json.loads(CONTENT.read_text(encoding="utf-8"))
        self.manual = self.content["manual"]

    def test_menu_covers_every_scenario_and_extra_from_the_content_source(self) -> None:
        text = run_menu()
        for section in self.manual["sections"]:
            self.assertIn(section["title"], text, section["id"])
            self.assertIn(section["say"][0], text, section["id"])
        extras = self.manual["extras"]
        self.assertTrue(extras)
        for group in extras:
            self.assertIn(group["label"], text)
            for example in group["say"]:
                self.assertIn(example, text)

    def test_menu_output_stays_human_readable(self) -> None:
        text = run_menu()
        for leaked in ("/api/", ".json", "/home/", "module_tree", "engineering_details"):
            self.assertNotIn(leaked, text)
        self.assertIn(self.content["content_version"], text)

    def test_single_scenario_returns_full_scope_including_boundaries(self) -> None:
        section = self.manual["sections"][3]
        text = run_menu("--scenario", section["id"])
        self.assertIn(section["title"], text)
        self.assertIn(section["get"], text)
        self.assertIn(section["not_for"], text)

    def test_unknown_scenario_lists_available_ids_instead_of_failing_silently(self) -> None:
        text = run_menu("--scenario", "not-a-scenario")
        for section in self.manual["sections"]:
            self.assertIn(section["id"], text)

    def test_skill_menu_points_at_the_single_source_and_keeps_no_copy(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("## 引导与菜单", text)
        menu_section = text.split("## 引导与菜单", 1)[1].split("\n## ", 1)[0]

        self.assertIn("scripts/xiaoxue_menu.py", menu_section)
        self.assertIn("不另抄功能清单", menu_section)
        for group in self.manual["extras"]:
            self.assertNotIn(group["label"], menu_section)
            for example in group["say"]:
                self.assertNotIn(example, menu_section)

    def test_manual_extras_keep_the_phrases_users_actually_say(self) -> None:
        labels = {group["label"] for group in self.manual["extras"]}
        self.assertEqual(labels, {"周期扫描", "盘口判断", "分析师", "其他电竞", "研究底稿"})
        for group in self.manual["extras"]:
            self.assertTrue(group["say"])

    def test_module_list_reads_the_same_source_as_the_project_center(self) -> None:
        tree = json.loads(CONTENT.read_text(encoding="utf-8"))["module_tree"]
        text = run_menu("--modules")
        for node in tree:
            self.assertIn(node["name"], text, node["id"])
            self.assertIn(node["purpose"], text, node["id"])

    def test_single_module_returns_capability_and_boundary(self) -> None:
        node = json.loads(CONTENT.read_text(encoding="utf-8"))["module_tree"][2]
        text = run_menu("--module", node["id"])
        for key in ("purpose", "when_to_use", "current_capability", "boundaries", "next_step"):
            self.assertIn(node[key], text, key)

    def test_model_guide_points_at_the_source_instead_of_copying_the_module_table(self) -> None:
        guide = GUIDE.read_text(encoding="utf-8")
        self.assertIn("scripts/xiaoxue_menu.py --modules", guide)
        self.assertIn("module_tree", guide)
        self.assertNotIn("| 模块 | 钧钧用它解决什么 |", guide)
        self.assertNotIn("| TS／队伍实力展示 |", guide)


if __name__ == "__main__":
    unittest.main()
