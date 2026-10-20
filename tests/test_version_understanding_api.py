import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main


FIXTURE_CONTENT = """# 版本理解（统一篮子）

## 版本主线 · 第三赛段（骨架更新版）

总纲：进攻是唯一主旋律。

**① 节奏中野**：中野先落位，资源置换后锁死视野。

---

# 各段日期时间线
"""


class VersionUnderstandingApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_path = os.environ.get("XIAOXUE_DB_PATH")
        self.database = Path(self.directory.name) / "version-understanding.sqlite3"
        self._create_fixture()
        os.environ["XIAOXUE_DB_PATH"] = str(self.database)
        self.client = TestClient(main.app)

    def tearDown(self):
        if self.previous_path is None:
            os.environ.pop("XIAOXUE_DB_PATH", None)
        else:
            os.environ["XIAOXUE_DB_PATH"] = self.previous_path
        self.directory.cleanup()

    def test_global_current_returns_only_the_unified_object_and_current_mainline(self):
        response = self.client.get("/api/version-understanding/global/current")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        item = payload["data"]["item"]
        self.assertEqual(item["id"], 229)
        self.assertEqual(item["topic"], "版本理解-统一篮子（fixture）")
        self.assertEqual(item["content_type"], "version_meta")
        self.assertIn("第三赛段", payload["data"]["current_mainline"]["content"])
        self.assertIn("节奏中野", payload["data"]["current_mainline"]["content"])
        self.assertTrue(payload["effects"]["read_only"])
        self.assertEqual(payload["effects"]["database_writes"], 0)

    def test_global_current_has_an_explicit_empty_state(self):
        connection = sqlite3.connect(self.database)
        connection.execute("DELETE FROM shared_version_analysis")
        connection.commit()
        connection.close()

        response = self.client.get("/api/version-understanding/global/current")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "empty")
        self.assertIsNone(response.json()["data"]["item"])

    def _create_fixture(self):
        connection = sqlite3.connect(self.database)
        connection.execute("""CREATE TABLE shared_version_analysis (
            id INTEGER PRIMARY KEY,
            source_category TEXT NOT NULL,
            topic TEXT,
            content TEXT NOT NULL,
            created_at TEXT,
            content_type TEXT
        )""")
        connection.execute(
            """INSERT INTO shared_version_analysis
               (id, source_category, topic, content, created_at, content_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (229, "版本理解", "版本理解-统一篮子（fixture）", FIXTURE_CONTENT, "2026-08-19 02:40:00", "version_meta"),
        )
        connection.commit()
        connection.close()


if __name__ == "__main__":
    unittest.main()
