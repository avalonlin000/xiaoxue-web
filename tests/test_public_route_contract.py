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
            ("GET", "/api/profile-full/{team}"),
            ("GET", "/api/version-understanding/{team}"),
            ("GET", "/api/tk/library"),
            ("GET", "/api/tk/entry/{filename}"),
            ("GET", "/api/daily-content"),
            ("GET", "/api/current-event"),
            ("GET", "/api/market-notes"),
            ("POST", "/api/market-notes"),
            ("POST", "/api/lineup-workflow/prepare"),
        }
        counts = Counter(
            (method, route.path)
            for route in main.app.routes
            for method in (getattr(route, "methods", None) or set())
            if method in {"GET", "POST", "PUT", "DELETE"}
        )
        for contract in expected:
            with self.subTest(contract=contract):
                self.assertEqual(counts[contract], 1)


if __name__ == "__main__":
    unittest.main()
