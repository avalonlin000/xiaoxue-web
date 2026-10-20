import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from xiaoxue_api.modules.market_notes import repository as market_repository


class ApiModuleIsolationTests(unittest.TestCase):
    def test_retired_market_notes_write_does_not_block_lineup(self):
        lineup_payload = {
            "match_name": "A vs B", "blue_team": "A", "red_team": "B",
            "blue_lineup": {"TOP": "a", "JUNGLE": "b", "MID": "c", "BOT": "d", "SUPPORT": "e"},
            "red_lineup": {"TOP": "f", "JUNGLE": "g", "MID": "h", "BOT": "i", "SUPPORT": "j"},
        }
        with TestClient(main.app) as client:
            retired = client.post("/api/market-notes", json={"game": "lol", "match_name": "模块隔离测试"})
            lineup = client.post("/api/lineup-workflow/prepare", json=lineup_payload)

        self.assertEqual(retired.status_code, 410)
        self.assertEqual(lineup.status_code, 200)
        self.assertTrue(lineup.json()["ready"])

    def test_market_tk_projection_does_not_query_retired_database_table(self):
        with patch.object(
            market_repository,
            "connect",
            side_effect=sqlite3.OperationalError("retired database unavailable"),
        ), TestClient(main.app) as client:
            market = client.get("/api/market-notes")

        self.assertEqual(market.status_code, 200)
        self.assertEqual(market.json()["source"], "trading_tk")


if __name__ == "__main__":
    unittest.main()
