import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDES = {
    "lol.md": ("五项画像", "纯十英雄", "赛前"),
    "football.md": ("默认候选", "半破", "75 分钟后"),
    "cs2.md": ("地图", "本场", "盘口"),
    "valorant.md": ("适用条件", "实时价格", "原文"),
}
SUPERSEDED_PLANS = (
    "品种业务指导与文档整理方案.md",
    "赛前方法引导与主要矛盾判断-PRD.md",
    "项目中心开发模块更新-PRD.md",
)
SECTION_TITLES = (
    "用户要什么",
    "怎样使用",
    "先展示什么",
    "怎样判断",
    "资料和能力边界",
    "怎样验收",
)


class BusinessGuideTests(unittest.TestCase):
    def test_each_variety_has_the_six_required_business_topics(self):
        for filename in GUIDES:
            text = (ROOT / "docs/business" / filename).read_text(encoding="utf-8")
            headings = re.findall(r"^## \d+\. (.+)$", text, flags=re.MULTILINE)
            self.assertEqual(headings[:6], list(SECTION_TITLES), filename)

    def test_guides_keep_variety_specific_content_instead_of_templates(self):
        for filename, terms in GUIDES.items():
            text = (ROOT / "docs/business" / filename).read_text(encoding="utf-8")
            for term in terms:
                self.assertIn(term, text, f"{filename} missing {term}")

    def test_root_entry_and_index_link_every_guide(self):
        for entry in (ROOT / "AGENTS.md", ROOT / "docs/README.md"):
            text = entry.read_text(encoding="utf-8")
            for filename in GUIDES:
                self.assertIn(filename, text, f"{entry.name} missing {filename}")

    def test_superseded_business_plans_are_archived_and_not_active(self):
        for filename in SUPERSEDED_PLANS:
            self.assertFalse((ROOT / "docs/requirements" / filename).exists(), filename)
            self.assertTrue((ROOT / "docs/archive/designs" / filename).is_file(), filename)

        maintenance = (ROOT / "docs/architecture/PROJECT-CENTER-MODULE-MAINTENANCE.md").read_text(encoding="utf-8")
        self.assertIn("docs/archive/designs/项目中心开发模块更新-PRD.md", maintenance)
        self.assertNotIn("docs/requirements/项目中心开发模块更新-PRD.md", maintenance)

    def test_local_markdown_links_in_new_guidance_resolve(self):
        for entry in (
            ROOT / "AGENTS.md",
            ROOT / "docs/README.md",
            *(ROOT / "docs/business" / filename for filename in GUIDES),
        ):
            text = entry.read_text(encoding="utf-8")
            for raw_target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                target = raw_target.split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (entry.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"{entry}: broken link {raw_target}")


if __name__ == "__main__":
    unittest.main()
