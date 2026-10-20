"""当前赛事看板对「对阵未定」占位行的回归测试。

背景（2026-10-16 虚拟数据衔接调查）：S16 全球总决赛的赛程在队伍产生前是 TBD vs TBD。
旧实现把每一场都塞进严格对阵校验，占位行直接抛错，导致这些日期的整个看板 400。
现在未定对阵是看板上的正常「待定」条目，不进需要真实对阵的链路。
看板同时只显示当前赛事范围（current_event/config.json 的 leagues）内的赛程。
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from xiaoxue_api.modules.current_event import service


PLACEHOLDER_ROW = {
    "date": "2026-10-17", "time": "2026-10-17 02:00:00", "team_a": "TBD", "team_b": "TBD",
    "region": "国际", "format": "BO5", "stage": "S16全球总决赛",
}
CONCRETE_ROW = {
    "date": "2026-10-17", "time": "2026-10-17 17:00:00", "team_a": "BLG", "team_b": "WE",
    "region": "国际", "format": "BO5", "stage": "S16全球总决赛",
}
OUT_OF_SCOPE_ROW = {
    "date": "2026-10-17", "time": "2026-10-17 17:00:00", "team_a": "BFX", "team_b": "WE",
    "region": "国际", "format": "BO5", "stage": "德玛西亚杯",
}


class UnresolvedMatchupTests(unittest.TestCase):
    def test_placeholder_and_missing_or_identical_sides_are_unresolved(self):
        for left, right in (("TBD", "TBD"), ("tbd", "TBD"), ("", "BLG"), ("BLG", ""), ("BLG", "blg"), ("待定", "WE")):
            with self.subTest(left=left, right=right):
                self.assertTrue(service.is_unresolved_matchup(left, right))

    def test_two_real_teams_are_resolved(self):
        self.assertFalse(service.is_unresolved_matchup("BLG", "WE"))


class DashboardPendingTests(unittest.TestCase):
    def test_dashboard_survives_a_day_that_contains_a_tbd_row(self):
        with patch.object(service, "list_schedules", return_value=[PLACEHOLDER_ROW, CONCRETE_ROW]):
            payload = service.get_current_event_dashboard("2026-10-17", 12)

        matches = payload["matches"]
        self.assertEqual(len(matches), 2)
        self.assertTrue(matches[0]["pending"])
        self.assertFalse(matches[0]["ts"]["available"])
        self.assertIsNone(matches[0]["trade_plan"])
        self.assertIn("TBD", matches[0]["match"]["team_a"])
        self.assertFalse(matches[1]["pending"])

    def test_pending_row_never_enters_strict_identity_validation(self):
        with patch.object(service, "list_schedules", return_value=[PLACEHOLDER_ROW]):
            summary = service.get_current_event_dashboard("2026-10-17", 12)["matches"][0]

        self.assertEqual(summary.get("pending_reason"), "对阵未定：赛程已排期，双方队伍待产生")

    def test_concrete_matchup_still_reports_as_playable(self):
        with patch.object(service, "list_schedules", return_value=[CONCRETE_ROW]):
            summary = service.get_current_event_dashboard("2026-10-17", 12)["matches"][0]

        self.assertFalse(summary["pending"])
        self.assertIn("ts", summary)

    def test_dashboard_excludes_rows_outside_current_event_scope(self):
        with patch.object(service, "list_schedules", return_value=[PLACEHOLDER_ROW, OUT_OF_SCOPE_ROW]):
            payload = service.get_current_event_dashboard("2026-10-17", 12)

        matches = payload["matches"]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["pending"])
        self.assertEqual(matches[0]["match"]["stage"], "S16全球总决赛")


if __name__ == "__main__":
    unittest.main()
