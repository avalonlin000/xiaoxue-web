from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.core import database
from xiaoxue_api.modules.current_event import service as current_event_service


IDENTITY = {
    "team_a": "HLE", "team_b": "DK", "event": "LCK", "match_date": "2026-07-30",
    "match_time": "18:00", "match_format": "BO3",
}


class MatchRunContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "match-run.db")
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_non_lol_match_run_is_persisted_and_reopened_without_lol_schedule_lookup(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            started = current_event_service.start_match_run({
                "game": "valorant", "team_a": "T1", "team_b": "NRG",
                "event": "VCT", "match_date": "2026-10-10", "match_time": "19:00",
                "match_format": "BO3", "mode": "virtual_pre",
            })
            reopened = current_event_service.get_match_run({
                "game": "valorant", "team_a": "T1", "team_b": "NRG",
                "event": "changed label", "match_date": "2026-10-10", "match_time": "19:00",
                "match_format": "BO3",
            })
        self.assertEqual(started["match"]["game"], "valorant")
        self.assertEqual(started["id"], reopened["id"])
        self.assertTrue(reopened["exists"])

    def test_three_games_keep_entries_separate_and_resume_after_pause(self):
        ids = []
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            for game in ("lol", "valorant", "cs2"):
                identity = {**IDENTITY, "game": game}
                started = current_event_service.start_match_run(identity)
                ids.append(started["id"])
                current_event_service.save_match_trade_entry({
                    **identity, "section": "review", "content": f"{game} isolated review",
                })
                current_event_service.pause_match_run(identity)
            for game, run_id in zip(("lol", "valorant", "cs2"), ids):
                identity = {**IDENTITY, "game": game}
                resumed = current_event_service.start_match_run(identity)
                self.assertEqual(resumed["id"], run_id)
                self.assertEqual(resumed["entries"][0]["content"], f"{game} isolated review")
                self.assertEqual(resumed["activity_status"], "active")
        self.assertEqual(len(set(ids)), 3)

    def test_virtual_run_keeps_result_sealed_and_exposes_actionable_fact_statuses(self):
        facts = [
            {
                "kind": "qualitative", "label": "HLE 三维", "value": "稳定压制",
                "source": "team_3d", "source_ref": "HLE", "as_of": "2026-05-28",
                "status": "stale", "affects": "队伍风格", "action": "补 Score 最近五场 / 排除本场 / 用你的观察替换",
            },
            {
                "kind": "quantitative", "label": "当前 TS", "value": "HLE 28.0 / DK 25.0",
                "source": "team_ts", "source_ref": "HLE,DK", "as_of": "2026-07-31",
                "status": "excluded", "affects": "强弱判断", "action": "赛后值，赛前模拟不采用",
            },
        ]
        with patch.object(current_event_service, "_collect_run_facts", return_value=facts):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "virtual_pre"})

        self.assertEqual(started["mode"], "virtual_pre")
        self.assertEqual(started["phase"], "fact_check")
        self.assertFalse(started["result_unlocked"])
        self.assertEqual(started["facts"][0]["status"], "needs_review")
        self.assertTrue(started["guide"]["can_jump"])

    def test_fact_timestamp_never_automatically_marks_a_fact_stale_or_excluded(self):
        team_evidence = {
            "starters": [{"role": "TOP", "name": "Player"}],
            "three_dimensional": {
                "items": [{"label": "风格", "value": "前期主动"}],
                "version_understanding": "", "updated_at": "2026-05-01 10:00:00",
            },
        }
        with (
            patch.object(current_event_service.repository, "get_score_schedule", return_value=None),
            patch.object(current_event_service.repository, "list_score_team_form", return_value=[]),
            patch.object(current_event_service, "_team_evidence", return_value=team_evidence),
            patch.object(current_event_service, "_trading_notes", return_value=[]),
            patch.object(current_event_service, "get_match_context", return_value={"team_a": {"team": "HLE", "ts": 28}, "team_b": {"team": "DK", "ts": 25}}),
        ):
            facts = current_event_service._collect_run_facts(IDENTITY, "2026-07-30 18:00:00", "virtual_pre")

        d3 = next(item for item in facts if item["fact_code"] == "E12")
        ts = next(item for item in facts if item["fact_code"] == "E31")
        self.assertEqual(d3["status"], "active")
        self.assertNotIn("过时", d3["action"])
        self.assertEqual(ts["status"], "active")
        self.assertNotIn("排除", ts["action"])

    def test_user_correction_updates_only_the_affected_fact_and_leaves_judgment_empty(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[
            {
                "kind": "qualitative", "label": "HLE 三维", "value": "稳定压制",
                "source": "team_3d", "source_ref": "HLE", "as_of": "2026-05-28",
                "status": "stale", "affects": "队伍风格", "action": "补 Score 最近五场",
            },
        ]):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "virtual_pre"})

        changed = current_event_service.update_match_run_fact({
            **IDENTITY, "fact_id": started["facts"][0]["id"], "status": "excluded",
            "value": "赛前不采用这条旧三维", "reason": "资料过时，先排除",
        })
        loaded = current_event_service.get_match_run(IDENTITY)

        self.assertEqual(changed["fact"]["status"], "excluded")
        self.assertEqual(loaded["facts"][0]["value"], "赛前不采用这条旧三维")
        self.assertIsNone(loaded["virtual_judgment"])

    def test_score_result_is_independently_readable_without_a_match_run(self):
        current_event_service.repository.ensure_match_run_tables()
        with database.connect() as conn:
            conn.execute("""
                CREATE TABLE schedules (date TEXT, time_bjt TEXT, team_a TEXT, team_b TEXT, region TEXT,
                    format TEXT, stage TEXT, source TEXT, updated_at TEXT)
            """)
            conn.execute("""
                CREATE TABLE matches (match_id TEXT, team_a_id TEXT, team_b_id TEXT, match_time TEXT,
                    game_format TEXT, status TEXT, winner TEXT, score_a INTEGER, score_b INTEGER, updated_at TEXT, stage TEXT)
            """)
            conn.execute("""
                INSERT INTO schedules VALUES ('2026-07-30', '2026-07-30 18:00:00', 'HLE', 'DK', 'LCK',
                    'BO3', '第三赛段', 'scoregg:58294', '2026-07-30 10:00:00')
            """)
            conn.execute("""
                INSERT INTO matches VALUES ('scoregg_58294', 'HLE', 'DK', '2026-07-30 18:00:00', 'BO3',
                    'completed', 'DK', 1, 2, '2026-07-30 21:00:00', '第三赛段')
            """)

        standalone = current_event_service.get_score_match_result(IDENTITY)
        self.assertEqual(standalone["status"], "completed")
        self.assertEqual(standalone["result"]["winner"], "DK")
        self.assertIn("不读取或改变任何交易推演状态", standalone["boundary"])
        self.assertFalse(current_event_service.get_match_run(IDENTITY)["exists"])

        after = current_event_service.get_score_match_evidence({**IDENTITY, "view": "post"})
        self.assertEqual(after["score_match"]["result"]["winner"], "DK")

    def test_one_kickoff_keeps_one_run_when_the_event_label_changes(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            first = current_event_service.start_match_run({**IDENTITY, "event": "LCK"})
            second = current_event_service.start_match_run({**IDENTITY, "event": "LCK 2026第三赛段"})

        self.assertEqual(first["id"], second["id"])

    def test_missing_chat_time_is_completed_from_schedule_before_the_run_is_stored(self):
        schedule = {
            "time_bjt": "2026-07-30 18:00:00", "format": "BO3", "region": "LCK", "stage": "第三赛段",
        }
        with (
            patch.object(current_event_service.repository, "get_score_schedule", return_value=schedule),
            patch.object(current_event_service, "_collect_run_facts", return_value=[]),
        ):
            first = current_event_service.start_match_run({**IDENTITY, "event": "", "match_time": "", "match_format": ""})
            second = current_event_service.start_match_run(IDENTITY)

        self.assertEqual(first["match"]["match_time"], "18:00")
        self.assertEqual(first["id"], second["id"])

    def test_score_form_uses_the_selected_teams_score_perspective(self):
        row = {
            "team_a_id": "DK", "team_b_id": "HLE", "score_a": 0, "score_b": 1,
        }
        self.assertEqual(current_event_service._relative_score(row, "HLE"), "1:0")

    def test_trade_sections_are_optional_and_can_be_saved_out_of_order(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        saved = current_event_service.save_match_trade_entry({
            **IDENTITY,
            "section": "entry",
            "content": "只有盘口回到可接受位置且首发不变时才考虑进入",
        })
        loaded = current_event_service.get_match_run(IDENTITY)

        self.assertEqual(saved["entries"][0]["section"], "entry")
        self.assertEqual(loaded["entries"][0]["content"], "只有盘口回到可接受位置且首发不变时才考虑进入")
        self.assertEqual(loaded["focus"], "entry")
        self.assertEqual(loaded["activity_status"], "active")

    def test_guide_groups_existing_section_ids_into_pre_live_and_post_stages(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "live", "focus": "lineup"})

        stages = started["guide"]["stages"]
        self.assertEqual(list(stages), ["pre", "live", "post"])
        self.assertEqual([item["id"] for item in stages["pre"]["modules"]], [
            "version", "team", "trend", "matchup", "branches", "market", "plan", "entry", "exit",
        ])
        self.assertEqual([item["id"] for item in stages["live"]["modules"]], ["lineup", "execution"])
        self.assertEqual([item["id"] for item in stages["post"]["modules"]], ["review"])
        self.assertEqual(started["focus"], "lineup")
        self.assertEqual(next(item for item in started["guide"]["modules"] if item["id"] == "lineup")["stage"], "live")

        saved = current_event_service.save_match_trade_entry({
            **IDENTITY, "section": "review", "content": "赛后只复盘这一场的判断和执行。",
        })
        self.assertEqual(saved["entries"][0]["section"], "review")
        self.assertEqual(saved["entries"][0]["stage"], "post")

    def test_new_match_opens_as_a_neutral_draft_instead_of_forcing_version_first(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        self.assertEqual(started["focus"], "overview")
        self.assertEqual(started["guide"]["focus_label"], "单场底稿")
        self.assertTrue(started["guide"]["can_jump"])
        self.assertNotIn("next", started["guide"])

    def test_unopened_or_inactive_match_never_returns_a_forced_next_step(self):
        unopened = current_event_service.get_match_run(IDENTITY)
        inactive = current_event_service.get_active_match_run()

        self.assertEqual(unopened["guide"]["focus"], "overview")
        self.assertTrue(unopened["guide"]["can_jump"])
        self.assertNotIn("next", unopened["guide"])
        self.assertTrue(inactive["guide"]["can_jump"])
        self.assertNotIn("next", inactive["guide"])

    def test_match_can_open_directly_at_any_requested_module_without_writing_a_judgment(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "live", "focus": "lineup"})
            switched = current_event_service.focus_match_run({**IDENTITY, "focus": "market"})

        self.assertEqual(started["focus"], "lineup")
        self.assertEqual(started["entries"], [])
        self.assertEqual(switched["focus"], "market")
        self.assertEqual(switched["entries"], [])

    def test_opened_match_exposes_only_its_own_tk_in_call_order(self):
        framework = {
            "call_order": ["全局", "赛区", "队伍/选手"],
            "items": [
                {"scope": "global", "statement": "版本前期资源更重要", "status": "confirmed"},
                {"scope": "region", "statement": "LCK 更偏资源运营", "status": "candidate"},
                {"scope": "team", "statement": "HLE 团战容易翻盘", "status": "confirmed"},
            ],
        }
        with (
            patch.object(current_event_service, "_collect_run_facts", return_value=[]),
            patch.object(current_event_service, "_match_trading_framework", return_value=framework),
        ):
            started = current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        self.assertEqual(started["trading_framework"]["call_order"], ["全局", "赛区", "队伍/选手"])
        self.assertEqual([item["scope"] for item in started["trading_framework"]["items"]], ["global", "region", "team"])
        self.assertEqual(started["trading_framework"]["items"][1]["status"], "candidate")

    def test_trend_entry_can_be_saved_without_user_confirmation(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        saved = current_event_service.save_match_trade_entry({
            **IDENTITY,
            "section": "trend",
            "content": "换人队近期更容易打出好表现",
        })
        self.assertEqual(saved["entries"][0]["section"], "trend")

    def test_opening_another_match_pauses_first_and_reopening_restores_it(self):
        second = {
            "team_a": "T1", "team_b": "GEN", "event": "LCK", "match_date": "2026-07-30",
            "match_time": "20:00", "match_format": "BO3",
        }
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            first = current_event_service.start_match_run({**IDENTITY, "mode": "live"})
            current_event_service.save_match_trade_entry({
                **IDENTITY, "section": "trend", "content": "HLE 当前更适合主动中野版本",
                "confirmed_by_user": True,
            })
            opened_second = current_event_service.start_match_run({**second, "mode": "live"})

        paused_first = current_event_service.get_match_run(IDENTITY)
        self.assertEqual(paused_first["activity_status"], "paused")
        self.assertEqual(opened_second["activity_status"], "active")

        reopened = current_event_service.start_match_run({**IDENTITY, "mode": "live"})
        self.assertEqual(reopened["id"], first["id"])
        self.assertEqual(reopened["activity_status"], "active")
        self.assertEqual(reopened["entries"][0]["content"], "HLE 当前更适合主动中野版本")

    def test_pause_keeps_the_thread_reopenable_without_marking_it_complete(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        paused = current_event_service.pause_match_run(IDENTITY)
        self.assertEqual(paused["activity_status"], "paused")
        self.assertNotEqual(paused.get("phase"), "complete")

    def test_long_term_candidate_targets_an_entity_or_method_not_the_match(self):
        with patch.object(current_event_service, "_collect_run_facts", return_value=[]):
            current_event_service.start_match_run({**IDENTITY, "mode": "live"})

        result = current_event_service.create_knowledge_candidate({
            **IDENTITY,
            "target_type": "team",
            "target_name": "HLE",
            "topic": "版本适应",
            "observation": "换人后中野主动性连续兑现",
            "reason": "可能改变对 HLE 当前版本适配的认识",
        })
        pending = current_event_service.list_knowledge_candidates("pending", 20)

        self.assertEqual(result["candidate"]["target_type"], "team")
        self.assertEqual(pending["candidates"][0]["target_name"], "HLE")
        with self.assertRaisesRegex(ValueError, "长期更新对象"):
            current_event_service.create_knowledge_candidate({
                **IDENTITY,
                "target_type": "match",
                "target_name": "HLE vs DK",
                "topic": "比赛",
                "observation": "这场打完了",
                "reason": "保存比赛笔记",
            })

if __name__ == "__main__":
    unittest.main()
