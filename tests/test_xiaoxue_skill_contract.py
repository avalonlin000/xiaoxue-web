from __future__ import annotations

import os
import unittest
from pathlib import Path


def _skill_path() -> Path:
    return Path(os.environ.get("XIAOXUE_SKILL_CANDIDATE", "/home/ubuntu/.agents/skills/小雪/SKILL.md"))


def _soul_path() -> Path:
    return Path(os.environ.get("XIAOXUE_SOUL_CANDIDATE", "/home/ubuntu/.hermes/SOUL.md"))


def _team_profile_root() -> Path:
    return Path(
        os.environ.get("XIAOXUE_TEAM_PROFILE_ROOT", "/home/ubuntu/.agents/skills")
    )


def _product_reference(name: str) -> Path:
    return _skill_path().parent / "references" / "product" / name


def _project_agents() -> Path:
    return Path(__file__).resolve().parents[1] / "AGENTS.md"


def _business_guide(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "business" / name


class XiaoxueSkillContractTests(unittest.TestCase):
    def test_soul_routes_natural_business_intent_without_an_execution_phrase(self) -> None:
        text = _soul_path().read_text(encoding="utf-8")

        self.assertIn("自然接住他的对象和问题，不要求先选模式、说口令或确认进入项目", text)
        self.assertIn("项目有自己的正式规则与数据，你按需使用和查看", text)
        self.assertIn("你保留完整业务使用与按需查看能力", text)
        self.assertNotIn("普通聊天只回答；明确要求执行才进入业务 Skill", text)
        self.assertNotIn("执行口令", text)

    def test_soul_aligns_recommendations_to_current_user_goal(self) -> None:
        text = _soul_path().read_text(encoding="utf-8")

        self.assertIn("先接住钧钧正在推进的判断，再补最关键的一环", text)
        self.assertIn("跟着当前思路讨论，不抢结论、不重启一份标准报告", text)
        self.assertIn("不为了全面扩展无关事项", text)
        self.assertIn("只查、只聊、只维护时就围绕该目标完成，不自动转成交易建议", text)
        self.assertIn("简单问题短答", text)
        self.assertIn("只有不同理解会显著改变结果、成本或副作用时，才问一个关键问题", text)

    def test_all_modules_use_semantic_intent_instead_of_magic_phrases(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("## 按意图选择", text)
        self.assertIn("只加载本轮需要的专项，不把表当流程", text)
        self.assertIn("日常直接接业务，不选模式", text)
        self.assertIn("沿当前对象和明确方法继续", text)
        self.assertIn("专项提供专业方法，回答形式服从本轮目标", text)
        self.assertIn("能力介绍以当前配置和实际工具为准", text)
        self.assertIn("项目规则见 `/home/ubuntu/xiaoxue-web/AGENTS.md`", text)
        self.assertNotIn("_PHRASES", text)
        self.assertNotIn("first_turn_brief", text)
        self.assertNotIn("/home/ubuntu/lol_data", text)
        self.assertNotIn("执行口令", text)

    def test_specialized_confirmation_stays_out_of_the_root_skill(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertNotIn("dispatch_pending_reply.py", text)
        self.assertIn("专项提供专业方法", text)
        self.assertIn("不复制另一套流程", _soul_path().read_text(encoding="utf-8"))

    def test_specialized_workflows_never_ask_for_an_exact_confirmation_phrase(self) -> None:
        paths = [
            Path(os.environ.get(
                "XIAOXUE_KNOWLEDGE_LOOP_SKILL_CANDIDATE",
                "/home/ubuntu/.agents/skills/esports/knowledge/xiaoxue-knowledge-loop/SKILL.md",
            )),
            Path(os.environ.get(
                "XIAOXUE_KNOWLEDGE_MAINTENANCE_SKILL_CANDIDATE",
                "/home/ubuntu/.agents/skills/esports/knowledge/xiaoxue-knowledge-maintenance/SKILL.md",
            )),
            Path(os.environ.get(
                "XIAOXUE_KNOWLEDGE_MAINTENANCE_TK_REF_CANDIDATE",
                "/home/ubuntu/.agents/skills/esports/knowledge/xiaoxue-knowledge-maintenance/references/tk.md",
            )),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertIn("--decision confirm", combined)
        self.assertIn("--decision defer", combined)
        self.assertIn("不要求固定句式", combined)
        self.assertNotIn("只有原话 `这批压缩通过`", combined)
        self.assertNotIn("收到原话 `这版通过`", combined)

    def test_external_news_uses_the_single_product_tool_and_canonical_routing_contract(self) -> None:
        root = _skill_path().read_text(encoding="utf-8")
        sources = _product_reference("help-and-sources.md").read_text(encoding="utf-8")
        routing = Path("/home/ubuntu/.agents/skills/engineering/xiaoxue-dev-index/references/search-routing.md").read_text(encoding="utf-8")

        self.assertIn("| 外部资料（external） | `references/product/help-and-sources.md` 的外部资料入口 |", root)
        self.assertNotIn("xiaoxue_search_external_news", root)
        self.assertIn("明确要最新、新闻、外部核对或搜索时执行只读搜索", sources)
        self.assertIn("search_web.py", sources)
        self.assertNotIn("xiaoxue_search_external_news", sources)
        self.assertIn("xiaoxue_search_external_news", routing)
        self.assertIn("Agent Reach 的 Exa", routing)
        self.assertIn("赔率/预测", routing)
        self.assertIn("发布时间", routing)
        self.assertIn("单轮只调用一次", routing)
        self.assertIn("不得从 Highlights", routing)

    def test_free_module_switching_reuses_the_match_open_tool(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("沿当前对象和明确方法继续", text)
        self.assertIn("只加载本轮需要的专项", text)
        self.assertNotIn("`focus`", text)
        self.assertNotIn("xiaoxue_start_match_run", text)
        self.assertNotIn("xiaoxue_focus_match_trade", text)

    def test_profile_only_requests_do_not_pull_in_other_modules(self) -> None:
        contract = (
            "用户只问队伍画像、首发或队伍资料时，只展示五项画像和明确请求的队伍事实；"
            "不自动读取或附加 TS、TK、盘口，以及 volatility/trend 等内部字段。"
            "只有用户明确要求组合时，才读取并展示对应模块。"
        )
        lol_guide = _business_guide("lol.md").read_text(encoding="utf-8")
        agents = _project_agents().read_text(encoding="utf-8")
        records = _product_reference("data-and-records.md").read_text(encoding="utf-8")

        self.assertIn(contract, lol_guide)
        self.assertNotIn(contract, agents)
        self.assertIn("单问画像、首发或队伍资料，只取五项画像及明确请求的事实，不附带 TS、TK、盘口或内部字段", records)
        self.assertIn("TS 用户结果用“综合实力、稳定性、趋势、势头、状态”", records)
        self.assertIn("不主动输出英文键、速度/加速度、波动度、原始量和历史数列", records)

    def test_lineup_without_bp_stops_honestly_and_keeps_project_access(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")
        lineup = Path("/home/ubuntu/.agents/skills/esports/lol-lineup-analysis/SKILL.md").read_text(encoding="utf-8")
        agents = _project_agents().read_text(encoding="utf-8")

        self.assertIn("| 纯十英雄阵容（lineup） | 先 `lol-competition-basics`，再 `lol-lineup-analysis`", text)
        self.assertIn("队名仅作蓝红方标签，不扩查比赛、赛程、队伍、TS、TK、盘口或新闻", text)
        self.assertIn("仅真正缺英雄或位置歧义才澄清", lineup)
        self.assertIn("不引入队伍资料、选手、赛果、TS、TK、盘口", lineup)
        self.assertIn("未知名称由程序标UNKNOWN，不猜", lineup)
        self.assertIn("这是自用的电竞交易辅助项目", agents)
        self.assertIn("小雪是当前接入助手之一", agents)

    def test_merged_team_profile_skill_covers_all_teams_without_overview_triggers(self) -> None:
        root = _team_profile_root()
        merged = root / "esports/teams/team-profiles/SKILL.md"
        self.assertTrue(merged.exists(), merged.as_posix())
        description = merged.read_text(encoding="utf-8").split("---", 2)[1]
        self.assertIn("普通比赛总览", description)
        self.assertIn("只有钧钧明确", description)
        self.assertIn("小雪根 Skill", description)

        refs = sorted((root / "esports/teams/team-profiles/references").glob("*.md"))
        self.assertEqual([path.stem for path in refs], [
            "al", "bfx", "blg", "bro", "dk", "dns", "edg", "gen", "hle", "ig", "jdg",
            "krx", "kt", "lgd", "lng", "nip", "ns", "t1", "tes", "tt", "wbg", "we",
        ])
        self.assertEqual(list(root.glob("*-team-profile")), [])


if __name__ == "__main__":
    unittest.main()
