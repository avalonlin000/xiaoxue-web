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


class XiaoxueSkillContractTests(unittest.TestCase):
    def test_soul_routes_natural_business_intent_without_an_execution_phrase(self) -> None:
        text = _soul_path().read_text(encoding="utf-8")

        self.assertIn("自然提到能识别的电竞对象或任务", text)
        self.assertIn("读取现有信息和建立可丢弃的临时上下文不要求执行口令", text)
        self.assertIn("产品能力支持的小范围业务写回不要求逐次确认", _soul_path().read_text(encoding="utf-8"))
        self.assertNotIn("普通聊天只回答；明确要求执行才进入业务 Skill", text)

    def test_soul_aligns_recommendations_to_current_user_goal(self) -> None:
        text = _soul_path().read_text(encoding="utf-8")

        self.assertIn("不以自己的默认方向替代钧钧明确的方法、限制或已经形成的结论", text)
        self.assertIn("当前明确目标 → 钧钧指定的方法与限制 → 可验证的当前事实", text)
        self.assertIn("不是罗列所有可做事项，也不为了显得全面扩展无关模块", text)
        self.assertIn("只查、只聊、只维护时不自动转成交易建议", text)
        self.assertIn("默认只说必需项", text)
        self.assertIn("我刚才把重点理解成 X，实际应是 Y", text)

    def test_all_modules_use_semantic_intent_instead_of_magic_phrases(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("自然使用合同", text)
        self.assertIn("动作后果与权限", text)
        self.assertIn("不需要说“执行、调用、打开、开始分析、继续”等标准句式", text)
        self.assertIn("明确要求最新、外部、新闻、实时核对或搜索", text)
        self.assertIn("已有正源上的小范围保存、更新、整理", text)
        self.assertIn("普通单英雄/双英雄对位", text)
        self.assertIn("模型底座", text)
        self.assertIn("比如、例如", text)
        self.assertIn("只是举例、不要打开、先聊方法", text)
        self.assertIn("这些是能力，不是固定步骤", text)
        self.assertIn("辅助通用能力：保留但不抢答", text)
        self.assertIn("默认先用最贴近的 `xiaoxue-product`", text)
        self.assertIn("明确要求最新、外部、新闻、实时核对或搜索时，直接执行只读搜索", text)
        self.assertNotIn("_PHRASES", text)
        self.assertNotIn("first_turn_brief", text)
        self.assertNotIn("/home/ubuntu/lol_data", text)

    def test_specialized_confirmation_stays_out_of_the_root_skill(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertNotIn("dispatch_pending_reply.py", text)
        self.assertIn("专项 Skill", text)
        self.assertIn("高风险动作", text)

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
        routing = Path("/home/ubuntu/.agents/skills/engineering/xiaoxue-dev-index/references/search-routing.md").read_text(encoding="utf-8")

        self.assertIn("新的外部搜索", root)
        self.assertNotIn("xiaoxue_search_external_news", root)
        self.assertIn("xiaoxue_search_external_news", routing)
        self.assertIn("Agent Reach 的 Exa", routing)
        self.assertIn("赔率/预测", routing)
        self.assertIn("发布时间", routing)
        self.assertIn("单轮只调用一次", routing)
        self.assertIn("不得从 Highlights", routing)

    def test_free_module_switching_reuses_the_match_open_tool(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")

        self.assertIn("建立、切换、暂停、恢复临时上下文", text)
        self.assertIn("模型根据当前问题自由选择和组合", text)
        self.assertNotIn("`focus`", text)
        self.assertNotIn("xiaoxue_start_match_run", text)
        self.assertNotIn("xiaoxue_focus_match_trade", text)

    def test_profile_only_requests_do_not_pull_in_other_modules(self) -> None:
        contract = (
            "用户只问队伍画像、首发或队伍资料时，只展示五项画像和明确请求的队伍事实；"
            "不自动读取或附加 TS、TK、盘口，以及 volatility/trend 等内部字段。"
            "只有用户明确要求组合时，才读取并展示对应模块。"
        )
        texts = "\n".join((
            _skill_path().read_text(encoding="utf-8"),
            (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8"),
        ))

        self.assertEqual(texts.count(contract), 2)
        self.assertIn(
            "队伍画像、首发、队伍资料单问不附加 TS、TK、盘口或内部字段",
            _skill_path().read_text(encoding="utf-8").split("---", 2)[2],
        )
        self.assertIn("TS 的普通用户结果只用“综合实力、稳定性、趋势、势头、状态”五个固定中文名称", _skill_path().read_text(encoding="utf-8"))
        self.assertIn("不主动输出“实力分”“波动/波动度”、英文键、速度/加速度、原始量或历史数列", texts)

    def test_lineup_without_bp_stops_honestly_and_keeps_project_access(self) -> None:
        text = _skill_path().read_text(encoding="utf-8")
        lineup = Path("/home/ubuntu/.agents/skills/esports/lol-lineup-analysis/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("纯十英雄阵容：`lol-lineup-analysis`", text)
        self.assertIn("仅真正缺英雄或位置歧义才澄清", lineup)
        self.assertIn("不引入队伍资料、选手、赛果、TS、TK、盘口", lineup)
        self.assertIn("未知名称由程序标UNKNOWN，不猜", lineup)
        self.assertIn("交易人生项目是电竞业务的正源与交付主体", text)
        self.assertIn("小雪是当前接入助手之一", text)

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
