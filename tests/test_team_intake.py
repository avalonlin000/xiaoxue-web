"""外部事实入库（team_intake）回归测试。

覆盖：必须带来源、库外队伍身份+首发入库后覆盖面缺口关闭、来源留痕可见、
已有事实不被覆盖、重复入库幂等。
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.core import database
from xiaoxue_api.modules.business_mutations import service as mutations
from xiaoxue_api.modules.lol_scope import service as scope

LEAGUE = "S16全球总决赛"

SCHEMA = """
CREATE TABLE teams (
    team_id TEXT PRIMARY KEY, name TEXT, short_name TEXT, region TEXT, league_id TEXT,
    status TEXT, created_at TEXT, updated_at TEXT,
    source_kind TEXT NOT NULL DEFAULT '', source_ref TEXT NOT NULL DEFAULT '',
    source_updated_at TEXT NOT NULL DEFAULT '', verified_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE rosters (
    id INTEGER PRIMARY KEY AUTOINCREMENT, roster_id TEXT, team_id TEXT, player_id TEXT,
    player_name TEXT, role TEXT, position TEXT, is_starter INTEGER, join_date TEXT,
    created_at TEXT, updated_at TEXT, leave_date TEXT, status TEXT, transfer_notes TEXT,
    source_kind TEXT NOT NULL DEFAULT 'legacy_unverified', source_ref TEXT NOT NULL DEFAULT '',
    source_updated_at TEXT NOT NULL DEFAULT '', verified_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE team_profiles (team_name TEXT PRIMARY KEY, updated_at TEXT);
CREATE TABLE schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time_bjt TEXT, team_a TEXT, team_b TEXT,
    region TEXT, format TEXT, stage TEXT, source TEXT, updated_at TEXT
);
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY, team_a_id TEXT, team_b_id TEXT, match_time TEXT, status TEXT,
    winner TEXT, score_a INTEGER, score_b INTEGER, created_at TEXT
);
"""

PLAYERS = [{"name": f"DEMO-{role}"} for role in ("TOP", "JGL", "MID", "BOT", "SUP")]
SOURCE = {"kind": "manual", "ref": "demo-not-real", "retrieved_at": "2026-10-17 00:20:00"}


class TeamIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "lol.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO schedules (date, time_bjt, team_a, team_b, region, format, stage, source, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (today, f"{today} 02:00:00", "C9", "FUR", "国际", "BO5", LEAGUE, "scoregg:1", f"{today} 09:00:00"),
        )
        conn.execute(
            "INSERT INTO teams (team_id, name, short_name, region, league_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            ("LPL-WE", "Team WE", "WE", "LPL", "LPL-2026-S2", "active", today, today),
        )
        conn.execute(
            "INSERT INTO rosters (roster_id, team_id, player_name, role, position, is_starter, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("roster-WE-1", "LPL-WE", "p1", "TOP", "TOP", 1, "active", today, today),
        )
        conn.commit()
        conn.close()
        self._patch = patch.object(database, "DB_PATH", self.db_path)
        self._patch.start()
        self._scope = patch.object(scope, "get_current_event_scope_leagues", return_value=[LEAGUE])
        self._scope.start()
        self._event = patch.object(scope, "get_current_event", return_value={"event": "S16 世界赛"})
        self._event.start()

    def tearDown(self):
        self._event.stop()
        self._scope.stop()
        self._patch.stop()
        self.tmp.cleanup()

    def intake(self, team="C9", **changes):
        payload = {"region": "INTL", "league_id": LEAGUE, "players": PLAYERS, "source": SOURCE}
        payload.update(changes)
        return mutations.apply_business_mutation(target_type="team_intake", target=team, changes=payload)

    def row(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, args).fetchone()
        finally:
            conn.close()

    def side(self, side_name):
        for item in scope.get_coverage("today", 1)["matches"]:
            for side, value in (item["lineup"]["sides"] or {}).items():
                if side == side_name:
                    return value
        return None

    def test_source_is_mandatory(self):
        with self.assertRaises(mutations.MutationRejected):
            mutations.apply_business_mutation(target_type="team_intake", target="C9", changes={"players": PLAYERS})

    def test_out_of_library_team_is_created_with_provenance(self):
        result = self.intake()
        self.assertTrue(result["created"])
        row = self.row("SELECT * FROM teams WHERE short_name='C9'")
        self.assertEqual(row["team_id"], "INTL-C9")
        self.assertEqual(row["source_kind"], "manual")
        self.assertEqual(row["source_ref"], "demo-not-real")
        self.assertEqual(row["source_updated_at"], "2026-10-17 00:20:00")
        self.assertEqual(row["verified_at"], "")
        starters = self.row("SELECT COUNT(*) AS n FROM rosters WHERE team_id='INTL-C9' AND is_starter=1 AND status='active'")
        self.assertEqual(starters["n"], 5)
        source_stamp = self.row("SELECT source_kind, source_ref FROM rosters WHERE team_id='INTL-C9' LIMIT 1")
        self.assertEqual(source_stamp["source_kind"], "manual")
        self.assertEqual(source_stamp["source_ref"], "demo-not-real")

    def test_coverage_gap_closes_after_intake(self):
        before = self.side("C9")
        self.assertEqual(before["status"], "missing")
        self.intake()
        after = self.side("C9")
        self.assertEqual(after["status"], "ok")
        self.assertEqual(after["gap"], "")

    def test_existing_identity_is_not_overwritten(self):
        self.intake(team="WE", name="Wrong Name", region="CN")
        row = self.row("SELECT * FROM teams WHERE short_name='WE'")
        self.assertEqual(row["name"], "Team WE")
        self.assertEqual(row["region"], "LPL")
        self.assertEqual(row["source_kind"], "manual")

    def test_repeat_intake_is_idempotent(self):
        self.intake()
        self.intake()
        rows = self.row("SELECT COUNT(*) AS n FROM teams WHERE short_name='C9'")
        self.assertEqual(rows["n"], 1)
        starters = self.row("SELECT COUNT(*) AS n FROM rosters WHERE team_id='INTL-C9' AND status='active'")
        self.assertEqual(starters["n"], 5)


class PriceFactTests(TeamIntakeTests):
    """外部价格留存：带来源才收，收完覆盖面自动不再报"没有价格来源"。"""

    def price(self, **changes):
        payload = {
            "team_a": "C9", "team_b": "FUR", "price_a": "1.85", "price_b": "2.05",
            "match_key": "scoregg_1",
            "source": {"kind": "manual", "ref": "demo-book", "recorded_at": "2026-10-17 01:00:00"},
        }
        payload.update(changes)
        return mutations.apply_business_mutation(target_type="lol_price", target="scoregg_1", changes=payload)

    def price_of(self, label="C9 vs FUR"):
        for item in scope.get_coverage("today", 1)["matches"]:
            if item["label"] == label:
                return item["price"]
        return None

    def test_price_requires_source(self):
        with self.assertRaises(mutations.MutationRejected):
            mutations.apply_business_mutation(
                target_type="lol_price", target="scoregg_1",
                changes={"team_a": "C9", "team_b": "FUR", "price_a": "1.85"},
            )

    def test_price_requires_pair_and_quote(self):
        with self.assertRaises(mutations.MutationRejected):
            self.price(team_b="")
        with self.assertRaises(mutations.MutationRejected):
            self.price(price_a="", price_b="")

    def test_coverage_reads_price_with_source(self):
        before = self.price_of()
        self.assertEqual(before["status"], "missing")
        self.price()
        after = self.price_of()
        self.assertEqual(after["status"], "ok")
        self.assertEqual(after["detail"], "1.85 / 2.05")
        self.assertIn("manual:demo-book@2026-10-17 01:00", after["source"])
        self.assertEqual(after["gap"], "")
        payload = scope.get_coverage("today", 1)
        self.assertTrue(payload["price_source_ready"])
        self.assertFalse(any("没有价格来源" in gap for gap in [g for item in payload["matches"] for g in item["gaps"]]))

    def test_second_quote_wins(self):
        self.price()
        self.price(price_a="1.70", price_b="2.20", source={"kind": "manual", "ref": "demo-book-2", "recorded_at": "2026-10-17 02:00:00"})
        after = self.price_of()
        self.assertEqual(after["detail"], "1.70 / 2.20")
        self.assertIn("demo-book-2", after["source"] or "")


if __name__ == "__main__":
    unittest.main()
