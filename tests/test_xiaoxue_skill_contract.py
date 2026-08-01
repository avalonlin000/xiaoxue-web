from __future__ import annotations

import os
import unittest
from pathlib import Path


def _skill_path() -> Path:
    return Path(os.environ.get("XIAOXUE_SKILL_CANDIDATE", "/home/ubuntu/.agents/skills/小雪/SKILL.md"))


class XiaoxueSkillContractTests(unittest.TestCase):
    def test_free_module_switching_reuses_the_match_open_tool(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("带入对应 `focus`", text)
        self.assertIn("复用同一工具", text)
        self.assertNotIn("xiaoxue_focus_match_trade", text)

    def test_lineup_without_bp_stops_honestly_without_generic_fallback(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("等 BP/十英雄再判断", text)
        self.assertIn("不得猜首发、翻内部数据库、查文件、调通用 terminal/API", text)
        self.assertIn("不得退回通用 terminal、文件搜索、直接数据库、内部接口或物理路径", text)


if __name__ == "__main__":
    unittest.main()
