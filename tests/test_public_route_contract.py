import unittest
from collections import Counter

import main


class PublicRouteContractTests(unittest.TestCase):
    def test_primary_routes_exist_once(self):
        expected = {
            ("GET", "/"),
            ("GET", "/api/health"),
            ("GET", "/api/teams"),
            ("GET", "/api/fundamentals/teams"),
            ("GET", "/api/fundamentals/match-context"),
            ("GET", "/api/profile-full/{team}"),
            ("GET", "/api/version-understanding/{team}"),
            ("GET", "/api/tk/library"),
            ("GET", "/api/tk/entry/{filename}"),
            ("GET", "/api/daily-content"),
            ("GET", "/api/current-event"),
            ("GET", "/api/current-event/dashboard"),
            ("GET", "/api/current-event/match-desk"),
            ("GET", "/api/current-event/match-run"),
            ("GET", "/api/current-event/match-run/active"),
            ("GET", "/api/current-event/match-runs"),
            ("POST", "/api/current-event/match-run/start"),
            ("POST", "/api/current-event/match-run/focus"),
            ("POST", "/api/current-event/match-run/pause"),
            ("PUT", "/api/current-event/match-run/entry"),
            ("POST", "/api/current-event/match-run/candidates"),
            ("GET", "/api/stage-review/candidates"),
            ("PATCH", "/api/stage-review/candidates/{candidate_id}"),
            ("GET", "/api/trading-tk"),
            ("POST", "/api/trading-tk"),
            ("PATCH", "/api/trading-tk/{filename}"),
            ("PUT", "/api/current-event/match-run/facts/{fact_id}"),
            ("POST", "/api/current-event/match-run/advance"),
            ("PUT", "/api/current-event/match-run/judgment"),
            ("POST", "/api/current-event/match-run/unlock-result"),
            ("GET", "/api/current-event/match-run/review"),
            ("GET", "/api/current-event/score-evidence"),
            ("GET", "/api/current-event/match-workspace"),
            ("PUT", "/api/current-event/match-workspace"),
            ("POST", "/api/current-event/match-workspace/changes"),
            ("GET", "/api/market-notes"),
            ("POST", "/api/market-notes"),
            ("POST", "/api/lineup-workflow/prepare"),
        }
        counts = Counter(
            (method, route.path)
            for route in main.app.routes
            for method in (getattr(route, "methods", None) or set())
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        )
        for contract in expected:
            with self.subTest(contract=contract):
                self.assertEqual(counts[contract], 1)


if __name__ == "__main__":
    unittest.main()
