"""lol_scope 范围派生与覆盖面计算的回归测试（只读能力）。

用临时数据库验证真实判断逻辑：范围过滤、库外队伍、对阵未定、赛后未入库、
未到结果时刻、首发陈旧，以及"LOL 没有价格来源"始终作为缺口暴露。
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.core import database
from xiaoxue_api.modules.lol_scope import service


SCHEMA = """
CREATE TABLE schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time_bjt TEXT, team_a TEXT, team_b TEXT,
    region TEXT, format TEXT, stage TEXT, source TEXT, updated_at TEXT
);
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY, team_a_id TEXT, team_b_id TEXT, match_time TEXT, status TEXT,
    winner TEXT, score_a INTEGER, score_b INTEGER, created_at TEXT
);
CREATE TABLE teams (
    team_id TEXT PRIMARY KEY, name TEXT, short_name TEXT, region TEXT, league_id TEXT, updated_at TEXT
);
CREATE TABLE rosters (
    id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT, player_name TEXT, is_starter INTEGER,
    status TEXT, leave_date TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE team_profiles (team_name TEXT PRIMARY KEY, updated_at TEXT);
"""

LEAGUE = "S16全球总决赛"


class ScopeCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "lol.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        now = datetime.now()
        fresh = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        stale = (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        conn.executemany(
            "INSERT INTO teams (team_id, name, short_name, region, league_id, updated_at) VALUES (?,?,?,?,?,?)",
            [("LPL-WE", "Team WE", "WE", "LPL", "LPL-2026-S2", fresh), ("LCK-T1", "T1", "T1", "LCK", "LCK-2026", fresh)],
        )
        conn.executemany(
            "INSERT INTO rosters (team_id, player_name, is_starter, status, leave_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            [("LPL-WE", "p1", 1, "active", "", fresh, fresh), ("LPL-WE", "p2", 1, "active", "", fresh, stale), ("LCK-T1", "p3", 1, "active", "", fresh, stale)],
        )
        conn.executemany(
            "INSERT INTO team_profiles (team_name, updated_at) VALUES (?,?)",
            [("Team WE", stale)],
        )
        past = (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        upcoming = (now + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        today = now.strftime("%Y-%m-%d")
        conn.executemany(
            "INSERT INTO schedules (date, time_bjt, team_a, team_b, region, format, stage, source, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (today, past, "WE", "T1", "国际", "BO5", LEAGUE, "scoregg:1", fresh),
                (today, past, "WE", "C9", "国际", "BO5", LEAGUE, "scoregg:2", fresh),
                (today, upcoming, "T1", "WE", "国际", "BO5", LEAGUE, "scoregg:3", fresh),
                (today, upcoming, "TBD", "TBD", "国际", "BO5", LEAGUE, "scoregg:4", fresh),
                (today, upcoming, "BFX", "WE", "国际", "BO5", "德玛西亚杯", "scoregg:5", fresh),
            ],
        )
        conn.execute(
            "INSERT INTO matches (match_id, team_a_id, team_b_id, match_time, status, winner, score_a, score_b, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("scoregg_1", "LPL-WE", "LCK-T1", past, "completed", "T1", 2, 3, fresh),
        )
        conn.commit()
        conn.close()
        self._patch = patch.object(database, "DB_PATH", self.db_path)
        self._patch.start()
        self._scope = patch.object(service, "get_current_event_scope_leagues", return_value=[LEAGUE])
        self._scope.start()
        self._event = patch.object(service, "get_current_event", return_value={"event": "S16 世界赛"})
        self._event.start()

    def tearDown(self):
        self._event.stop()
        self._scope.stop()
        self._patch.stop()
        self.tmp.cleanup()

    def _coverage(self):
        return service.get_coverage("today", 1)

    def _by_key(self, payload, key):
        return next(item for item in payload["matches"] if item["match_key"] == key)

    def test_scope_filters_out_other_events(self):
        keys = [item["match_key"] for item in self._coverage()["matches"]]
        self.assertEqual(sorted(keys), ["scoregg_1", "scoregg_2", "scoregg_3", "scoregg_4"])

    def test_scope_overview_derives_window_teams_without_tbd(self):
        overview = service.get_scope_overview()
        names = [team["name"] for team in overview["teams"]]
        self.assertEqual(sorted(names), ["C9", "T1", "WE"])
        self.assertEqual(overview["window"]["match_count"], 4)
        c9 = next(team for team in overview["teams"] if team["name"] == "C9")
        self.assertFalse(c9["in_library"])
        self.assertEqual(c9["gap"], "库内没有这支队")

    def test_missing_team_is_a_lineup_gap_not_silent(self):
        item = self._by_key(self._coverage(), "scoregg_2")
        self.assertEqual(item["lineup"]["status"], "missing")
        self.assertTrue(any("C9" in gap for gap in item["gaps"]))

    def test_stale_lineup_is_marked_with_age(self):
        item = self._by_key(self._coverage(), "scoregg_3")
        self.assertEqual(item["lineup"]["status"], "stale")
        self.assertEqual(item["lineup"]["sides"]["T1"]["status"], "stale")

    def test_result_after_expected_duration_is_gap(self):
        item = self._by_key(self._coverage(), "scoregg_2")
        self.assertEqual(item["result"]["status"], "missing")
        self.assertTrue(any("结果" in gap for gap in item["gaps"]))

    def test_result_before_due_is_pending_without_gap(self):
        item = self._by_key(self._coverage(), "scoregg_3")
        self.assertEqual(item["result"]["status"], "pending")
        self.assertFalse(any("结果" in gap for gap in item["gaps"]))

    def test_completed_result_reads_winner_and_time(self):
        item = self._by_key(self._coverage(), "scoregg_1")
        self.assertEqual(item["result"]["status"], "ok")
        self.assertEqual(item["result"]["winner"], "T1")
        self.assertTrue(item["result"]["recorded_at"])

    def test_unresolved_matchup_is_pending_and_not_a_gap(self):
        item = self._by_key(self._coverage(), "scoregg_4")
        self.assertEqual(item["lineup"]["status"], "pending")
        self.assertEqual(item["result"]["status"], "pending")
        self.assertTrue(item["gaps"])  # 只剩价格缺口
        self.assertTrue(all("TBD" not in gap for gap in item["gaps"]))

    def test_price_is_reported_missing_until_source_exists(self):
        payload = self._coverage()
        self.assertFalse(payload["price_source_ready"])
        for item in payload["matches"]:
            self.assertEqual(item["price"]["status"], "missing")
        self.assertEqual(payload["status"], "partial")

    def test_overview_is_read_only(self):
        before = Path(self.db_path).read_bytes()
        service.get_scope_overview()
        service.get_coverage("today", 3)
        self.assertEqual(before, Path(self.db_path).read_bytes())


if __name__ == "__main__":
    unittest.main()
