from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.modules.tk_knowledge import repository, service


class GeneralTradingTKTests(unittest.TestCase):
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

    def test_general_trading_tk_is_saved_in_the_existing_tk_library_and_read_back(self):
        created = service.create_general_trading_tk({
            "category": "roster",
            "statement": "最近换人的队伍更容易赢或发挥好",
            "context": "当前版本，后续继续验证",
            "source_command": "最近换人的队伍都在赢或者发挥好，帮我记着",
        })

        filename = created["item"]["filename"]
        self.assertTrue((Path(self.temp_dir.name) / filename).is_file())
        self.assertEqual(created["item"]["status"], "candidate")

        found = service.list_general_trading_tk(query="换人", status="candidate", limit=20)
        library = service.browse(period="all", query="换人", limit=20)

        self.assertEqual(found["items"][0]["statement"], "最近换人的队伍更容易赢或发挥好")
        self.assertEqual(found["items"][0]["filename"], filename)
        self.assertIn("通用交易 TK", library["results"][0]["tags"])

        updated = service.update_general_trading_tk_status(
            filename, "confirmed", "复查后确认可以继续使用",
        )
        self.assertEqual(updated["item"]["status"], "confirmed")
        self.assertEqual(
            service.list_general_trading_tk(query="换人", status="confirmed", limit=20)["items"][0]["filename"],
            filename,
        )

    def test_general_trading_tk_does_not_downgrade_when_remembered_again(self):
        created = service.create_general_trading_tk({
            "category": "lineup", "statement": "锁头多时更容易出现大人头",
            "context": "", "source_command": "帮我记着",
        })
        filename = created["item"]["filename"]
        service.update_general_trading_tk_status(filename, "confirmed", "已经复查")

        repeated = service.create_general_trading_tk({
            "category": "lineup", "statement": "锁头多时更容易出现大人头",
            "context": "出现强开阵容时", "source_command": "再帮我记着",
        })

        self.assertEqual(repeated["item"]["status"], "confirmed")
        self.assertEqual(repeated["item"]["context"], "出现强开阵容时")

    def test_trading_tk_keeps_scope_region_subject_and_version_in_one_library(self):
        created = service.create_general_trading_tk({
            "scope": "region", "region": "LCK", "version_context": "26.15",
            "category": "regional_style", "statement": "LCK 在当前版本更容易通过资源运营拉开差距",
            "context": "只在 26.15 的 LCK 对局中优先核对", "source_command": "LCK 这版本更偏运营，帮我记着",
        })

        found = service.list_general_trading_tk(
            query="运营", status="candidate", scope="region", region="LCK", version_context="26.15", limit=20,
        )

        item = found["items"][0]
        self.assertEqual(item["scope"], "region")
        self.assertEqual(item["region"], "LCK")
        self.assertEqual(item["version_context"], "26.15")
        self.assertEqual(item["category"], "regional_style")
        self.assertIn("赛区交易 TK", (Path(self.temp_dir.name) / created["item"]["filename"]).read_text(encoding="utf-8"))

    def test_match_lookup_orders_tk_from_global_to_region_team_and_player(self):
        entries = [
            {"scope": "global", "category": "version", "statement": "当前版本前期资源更重要", "source_command": "帮我记着"},
            {"scope": "region", "region": "LPL", "category": "regional_style", "statement": "LPL 更常主动提速", "source_command": "帮我记着"},
            {"scope": "team", "subject": "AL", "category": "team_style", "statement": "AL 团战更容易翻盘", "source_command": "帮我记着"},
            {"scope": "player", "subject": "Tarzan", "category": "player_style", "statement": "Tarzan 前期更主动找节奏", "source_command": "帮我记着"},
        ]
        for values in entries:
            filename = service.create_general_trading_tk(values)["item"]["filename"]
            service.update_general_trading_tk_status(filename, "confirmed", "验收确认")

        matched = service.list_match_trading_tk("LPL", ["AL", "TT"], ["Tarzan"], limit=20)

        self.assertEqual([item["scope"] for item in matched["items"]], ["global", "region", "team", "player"])
        self.assertEqual(matched["call_order"], ["全局", "赛区", "队伍/选手"])

    def test_confirmed_scoped_team_tk_stays_visible_with_existing_team_trading_notes(self):
        created = service.create_general_trading_tk({
            "scope": "team", "subject": "AL", "category": "team_style",
            "statement": "AL 团战容易翻盘", "source_command": "AL 团战容易翻盘，帮我记着",
        })
        service.update_general_trading_tk_status(created["item"]["filename"], "confirmed", "复查确认")

        with patch.object(service, "normalize_team", return_value="AL"):
            notes = service.list_team_trading_notes("AL", status="active", limit=20)

        self.assertEqual(notes["notes"][0]["original"], "AL 团战容易翻盘")
        self.assertEqual(notes["notes"][0]["source_type"], "scoped_trading_tk")

    def test_existing_team_trading_note_is_visible_in_unified_trading_tk_without_copying_it(self):
        legacy_filename = "manual_hle_trading_note.md"
        (Path(self.temp_dir.name) / legacy_filename).write_text("""---
source: 钧钧手动交易备注
type: trading_note
team: HLE
---

## 盘口 / 交易观察

### HLE 虐菜大人头
```yaml
team: HLE
type: trading_note
market: kills_over
scenario: stomp_weak_team
status: active
source: junjun_manual
```

原话：虐菜大人头

日报提示：虐菜大人头
""", encoding="utf-8")

        listed = service.list_general_trading_tk(scope="team", subject="HLE", status="confirmed", limit=20)
        matched = service.list_match_trading_tk("LCK", ["HLE", "T1"], [], limit=20)

        self.assertEqual(listed["items"][0]["statement"], "HLE：虐菜大人头")
        self.assertEqual(listed["items"][0]["filename"], legacy_filename)
        self.assertFalse(listed["items"][0]["editable"])
        self.assertEqual(matched["items"][0]["statement"], "HLE：虐菜大人头")


if __name__ == "__main__":
    unittest.main()
