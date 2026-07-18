import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from xiaoxue_api.core import database
from xiaoxue_api.modules.market_notes import service as market_service
from xiaoxue_api.modules.market_notes import repository as market_repository


class ApiModuleIsolationTests(unittest.TestCase):
    def test_broken_market_notes_config_does_not_block_lineup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = str(Path(temp_dir) / "isolated.db")
            broken_config = Path(temp_dir) / "broken-market-config.json"
            broken_config.write_text("{not-json", encoding="utf-8")

            with (
                patch.object(database, "DB_PATH", database_path),
                patch.object(market_service, "CONFIG_PATH", broken_config),
                TestClient(main.app) as client,
            ):
                market = client.post(
                    "/api/market-notes",
                    json={"game": "lol", "match_name": "模块隔离测试"},
                )
                lineup = client.post(
                    "/api/lineup-workflow/prepare",
                    json={
                        "match_name": "A vs B",
                        "blue_team": "A",
                        "red_team": "B",
                        "blue_lineup": {
                            "TOP": "a", "JUNGLE": "b", "MID": "c", "BOT": "d", "SUPPORT": "e",
                        },
                        "red_lineup": {
                            "TOP": "f", "JUNGLE": "g", "MID": "h", "BOT": "i", "SUPPORT": "j",
                        },
                    },
                )

            self.assertEqual(market.status_code, 503)
            self.assertEqual(lineup.status_code, 200)
            self.assertTrue(lineup.json()["ready"])

    def test_market_database_failure_does_not_block_lineup(self):
        lineup_payload = {
            "match_name": "A vs B", "blue_team": "A", "red_team": "B",
            "blue_lineup": {"TOP": "a", "JUNGLE": "b", "MID": "c", "BOT": "d", "SUPPORT": "e"},
            "red_lineup": {"TOP": "f", "JUNGLE": "g", "MID": "h", "BOT": "i", "SUPPORT": "j"},
        }
        with patch.object(
            market_repository,
            "connect",
            side_effect=sqlite3.OperationalError("database unavailable"),
        ), TestClient(main.app) as client:
            market = client.get("/api/market-notes")
            lineup = client.post("/api/lineup-workflow/prepare", json=lineup_payload)

        self.assertEqual(market.status_code, 503)
        self.assertEqual(lineup.status_code, 200)


if __name__ == "__main__":
    unittest.main()
