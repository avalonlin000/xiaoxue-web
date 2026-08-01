import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.core import database
from xiaoxue_api.modules.current_event import service as current_event_service
from xiaoxue_api.modules.fundamentals import service as fundamentals_service


def team_row(team: str, *, mu: float, sigma: float, seed_mu: float | None = None, seed_sigma: float | None = None):
    return {
        "short_name": team,
        "name": team,
        "region": "LPL",
        "mu": mu,
        "sigma": sigma,
        "final_seed_mu": seed_mu,
        "seed_sigma": seed_sigma,
        "seed_ts": (seed_mu - 3 * seed_sigma) if seed_mu is not None and seed_sigma is not None else None,
        "outright_odds_decimal": None,
        "note": "",
    }


class FundamentalsMatchContextTests(unittest.TestCase):
    def test_generic_match_uses_current_team_ts_instead_of_msi_seed(self):
        rows = {
            "A": team_row("A", mu=30, sigma=1, seed_mu=35, seed_sigma=2),
            "B": team_row("B", mu=26, sigma=1.5, seed_mu=25, seed_sigma=1),
        }
        with patch.object(fundamentals_service.repository, "get_ts_team", side_effect=lambda team: rows[team]):
            payload = fundamentals_service.get_match_context("A", "B", event="LPL 2026")

        self.assertEqual(payload["team_a"]["source"], "team_ts")
        self.assertEqual(payload["team_a"]["mu"], 30.0)
        self.assertEqual(payload["compare"]["mu_diff"], 4.0)

    def test_msi_match_keeps_msi_seed_when_available(self):
        rows = {
            "A": team_row("A", mu=30, sigma=1, seed_mu=35, seed_sigma=2),
            "B": team_row("B", mu=26, sigma=1.5, seed_mu=25, seed_sigma=1),
        }
        with patch.object(fundamentals_service.repository, "get_ts_team", side_effect=lambda team: rows[team]):
            payload = fundamentals_service.get_match_context("A", "B", event="MSI")

        self.assertEqual(payload["team_a"]["source"], "msi_seed")
        self.assertEqual(payload["team_a"]["mu"], 35.0)


class MatchDeskContractTests(unittest.TestCase):
    def test_match_desk_keeps_quantitative_and_qualitative_evidence_separate(self):
        context = {
            "event": "LPL", "team_a": {"team": "A"}, "team_b": {"team": "B"}, "compare": {"ts_diff": 2.4},
        }
        bundle = {
            "players": [{"name": "Top", "role": "TOP", "status": "首发"}],
            "three_dimensional": {
                "dim_1_name": "优势局", "dim_1_value": "控资源",
                "dim_2_name": "劣势局", "dim_2_value": "拖后期",
                "dim_3_name": "胜负手", "dim_3_value": "中野",
                "version_understanding": "当前版本偏前期", "updated_at": "2026-07-31",
            },
        }
        notes = {"notes": [{"title": "A 交易 TK", "daily_hint": "前期主动", "market_label": "独赢", "scenario": "前期"}]}
        with (
            patch.object(current_event_service, "get_match_context", return_value=context),
            patch.object(current_event_service, "get_profile_bundle", return_value=bundle),
            patch.object(current_event_service, "list_team_trading_notes", return_value=notes),
            patch.object(current_event_service, "list_match_trading_tk", return_value={
                "items": [{"scope": "global", "statement": "当前版本偏前期", "status": "confirmed"}],
                "call_order": ["全局", "赛区", "队伍/选手"],
            }),
            patch.object(current_event_service, "get_match_workspace", return_value={"exists": False, "current": None, "changes": []}),
        ):
            payload = current_event_service.get_match_desk("A", "B", "LPL")

        self.assertEqual(payload["quantitative"]["compare"]["ts_diff"], 2.4)
        self.assertEqual(payload["team_a"]["three_dimensional"]["items"][0], {"label": "优势局", "value": "控资源"})
        self.assertEqual(payload["trading_notes"]["team_b"][0]["hint"], "前期主动")
        self.assertEqual(payload["trading_framework"]["items"][0]["scope"], "global")
        self.assertNotIn("direction", payload)

    def test_dashboard_keeps_each_match_tied_to_its_schedule(self):
        config = {"event": "LPL", "phase": "第三赛段"}
        matches = [{"date": "2026-07-31", "team_a": "A", "team_b": "B", "stage": "LPL", "format": "BO3"}]
        with (
            patch.object(current_event_service.repository, "load_event_config", return_value=config),
            patch.object(current_event_service.repository, "read_plan", return_value=None),
            patch.object(current_event_service, "list_schedules", return_value=matches),
            patch.object(current_event_service, "get_match_context", return_value={"compare": {"ts_diff": 1}}),
        ):
            payload = current_event_service.get_current_event_dashboard("2026-07-31")

        self.assertEqual(payload["date"], "2026-07-31")
        self.assertEqual(payload["matches"][0]["match"]["team_a"], "A")
        self.assertTrue(payload["matches"][0]["ts"]["available"])


class MatchWorkspaceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "workspace.db")
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_workspace_saves_and_reads_a_short_current_judgment_for_one_match(self):
        saved = current_event_service.save_match_workspace({
            "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
            "match_time": "17:00", "match_format": "BO3", "direction": "A 小分",
            "reasons": "A 前期主动，B 中野近期衔接差", "handling": "等首局前十分钟",
            "change_conditions": "B 换回主力打野则取消",
        })

        loaded = current_event_service.get_match_workspace({
            "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
            "match_time": "17:00", "match_format": "BO3",
        })

        self.assertEqual(saved["current"]["direction"], "A 小分")
        self.assertEqual(loaded["current"]["handling"], "等首局前十分钟")
        self.assertEqual(loaded["changes"], [])

    def test_change_log_is_additive_and_never_silently_rewrites_current_judgment(self):
        identity = {
            "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
            "match_time": "17:00", "match_format": "BO3",
        }
        current_event_service.save_match_workspace({
            **identity, "direction": "A 胜", "reasons": "前期更稳定",
            "handling": "等BP", "change_conditions": "打野轮换则取消",
        })

        result = current_event_service.record_match_change({
            **identity, "source": "首发", "impact": "削弱", "detail": "A 打野临时轮换",
        })
        loaded = current_event_service.get_match_workspace(identity)

        self.assertEqual(result["change"]["impact"], "削弱")
        self.assertEqual(loaded["current"]["direction"], "A 胜")
        self.assertEqual(loaded["changes"][0]["detail"], "A 打野临时轮换")

    def test_change_requires_a_concrete_fact_instead_of_a_generic_risk_label(self):
        with self.assertRaisesRegex(ValueError, "变化内容不能为空"):
            current_event_service.record_match_change({
                "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
                "source": "盘口", "impact": "观察", "detail": "",
            })

    def test_schedule_timestamp_and_short_time_resolve_to_the_same_match_workspace(self):
        timestamp_identity = current_event_service.normalize_match_identity({
            "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
            "match_time": "2026-07-31 17:00:00", "match_format": "BO3",
        })
        short_identity = current_event_service.normalize_match_identity({
            "team_a": "A", "team_b": "B", "event": "LPL", "match_date": "2026-07-31",
            "match_time": "17:00", "match_format": "BO3",
        })

        self.assertEqual(timestamp_identity["match_time"], "17:00")
        self.assertEqual(timestamp_identity["match_key"], short_identity["match_key"])


if __name__ == "__main__":
    unittest.main()
