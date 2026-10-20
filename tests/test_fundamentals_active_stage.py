import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.core import database
from xiaoxue_api.modules.fundamentals import repository


class ActiveStageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "stage.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE ts_stage_snapshots(stage TEXT NOT NULL, region TEXT, team TEXT)")
        conn.execute("INSERT INTO ts_stage_snapshots(stage, region, team) VALUES ('第三赛段', 'LPL', 'BLG')")
        conn.commit()
        conn.close()
        self._patch = patch.object(database, "DB_PATH", str(self.db))
        self._patch.start()
        repository._STAGE_TOKENS_CACHE = None

    def tearDown(self):
        self._patch.stop()
        repository._STAGE_TOKENS_CACHE = None
        self._tmp.cleanup()

    def test_active_stage_follows_intl_snapshots(self):
        self.assertEqual(repository.active_stage(), "第三赛段")
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO ts_stage_snapshots(stage, region, team) VALUES ('国际赛', '国际', 'LGD')")
        conn.commit()
        conn.close()
        self.assertEqual(repository.active_stage(), "国际赛")

    def test_active_stage_reads_tokens_from_system_config(self):
        config_dir = Path(self._tmp.name) / "config"
        config_dir.mkdir()
        (config_dir / "system_config.json").write_text(
            '{"stage_tokens": {"ts_default_stage": "第一赛段", "ts_intl_stage": "国际赛"}}',
            encoding="utf-8",
        )
        repository._STAGE_TOKENS_CACHE = None
        self.assertEqual(repository.active_stage(), "第一赛段")


if __name__ == "__main__":
    unittest.main()
