from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.modules.tk_knowledge import repository, service


class UnifiedTKTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tk_dir_patch = patch.object(repository, "TK_DIR", self.temp_dir.name)
        self.reindex_patch = patch.object(repository, "request_reindex", return_value=True)
        self.tk_dir_patch.start()
        self.reindex_patch.start()

    def tearDown(self):
        self.reindex_patch.stop()
        self.tk_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_trade_is_distinct_reviewable_type_in_the_shared_tk_library(self):
        created = service.create_general_trading_tk({
            "scope": "team", "subject": "AL",
            "statement": "AL 团战容易翻盘", "source_command": "记一下交易 TK",
        })
        filename = created["filename"]
        raw = (Path(self.temp_dir.name) / filename).read_text(encoding="utf-8")
        self.assertIn("type: trading_note", raw)
        self.assertIn("status: candidate", raw)
        self.assertIn("## 交易 TK", raw)
        found = service.list_general_trading_tk(query="翻盘", scope="team", subject="AL", limit=20)
        self.assertEqual(found["items"][0]["type"], "trading_tk")
        self.assertEqual(found["items"][0]["status"], "candidate")

    def test_status_update_and_filter_do_not_change_ordinary_tk(self):
        created = service.create_general_trading_tk({
            "scope": "global", "statement": "前期线权稳定时资源更容易兑现", "source_command": "写进交易 TK",
        })
        service.update_general_trading_tk_status(created["filename"], "confirmed", "已有多场复核")
        confirmed = service.list_general_trading_tk(status="confirmed")
        self.assertEqual(len(confirmed["items"]), 1)
        self.assertEqual(confirmed["items"][0]["status"], "confirmed")
        ordinary = service.remember_personal_note("前期线权是重要观察信息", [])
        self.assertEqual(service.list_general_trading_tk(query="重要观察")["items"], [])
        self.assertTrue(Path(self.temp_dir.name, ordinary["filename"]).exists())

    def test_same_text_and_tags_is_idempotent(self):
        values = {"statement": "锁头多时更容易出现大人头", "source_command": "记一下交易 TK"}
        first = service.create_general_trading_tk(values)
        second = service.create_general_trading_tk(values)
        self.assertEqual(first["filename"], second["filename"])
        self.assertEqual(len(list(Path(self.temp_dir.name).glob("*.md"))), 1)

    def test_directional_tags_are_preserved_for_match_lookup(self):
        entries = [
            {"scope": "global", "statement": "当前版本前期资源更重要", "source_command": "记一下交易 TK"},
            {"scope": "region", "region": "LPL", "statement": "LPL 更常主动提速", "source_command": "记一下交易 TK"},
            {"scope": "team", "subject": "AL", "statement": "AL 团战更容易翻盘", "source_command": "记一下交易 TK"},
            {"scope": "player", "subject": "Tarzan", "statement": "Tarzan 前期更主动找节奏", "source_command": "记一下交易 TK"},
        ]
        for values in entries:
            service.create_general_trading_tk(values)
        matched = service.list_match_trading_tk("LPL", ["AL", "TT"], ["Tarzan"], limit=20)
        self.assertEqual([item["scope"] for item in matched["items"]], ["global", "region", "team", "player"])
        self.assertTrue(all("交易" in item["tags"] for item in matched["items"]))

    def test_team_projection_keeps_trading_type_boundary(self):
        service.create_general_trading_tk({
            "scope": "team", "subject": "AL", "statement": "AL 团战容易翻盘", "source_command": "记一下交易 TK",
        })
        notes = service.list_team_trading_notes("AL", status="all", limit=20)
        self.assertEqual(notes["notes"][0]["original"], "AL 团战容易翻盘")
        self.assertEqual(notes["notes"][0]["source_type"], "scoped_trading_tk")


if __name__ == "__main__":
    unittest.main()
