import unittest
from collections import Counter

import main


class PublicRouteContractTests(unittest.TestCase):
    def test_health_shows_research_archive_as_retired_module(self):
        response = main.app.routes
        self.assertTrue(response)
        from xiaoxue_api.modules.platform.service import health

        payload = health()
        self.assertEqual(payload["modules"]["research_subjects"]["status"], "disabled")
        self.assertEqual(payload["capabilities"]["research_subjects"]["effect"], "write")
        self.assertEqual(payload["capabilities"]["current_event"]["effect"], "temporary")

    def test_primary_routes_exist_once(self):
        expected = {
            ("GET", "/"),
            ("GET", "/api/health"),
            ("GET", "/api/modules"),
            ("GET", "/api/teams"),
            ("GET", "/api/fundamentals/teams"),
            ("GET", "/api/fundamentals/match-context"),
            ("GET", "/api/ts-updates/{team}"),
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
            ("GET", "/api/scoregg/result"),
            ("GET", "/api/scoregg/results"),
            ("GET", "/api/current-event/match-workspace"),
            ("PUT", "/api/current-event/match-workspace"),
            ("POST", "/api/current-event/trade-plan/manual"),
            ("POST", "/api/current-event/match-workspace/changes"),
            ("POST", "/api/lineup-workflow/prepare"),
            ("POST", "/api/research/subjects"),
            ("GET", "/api/research/subjects"),
            ("GET", "/api/research/subjects/{subject_id}"),
            ("POST", "/api/research/subjects/{subject_id}/events"),
            ("POST", "/api/research/subjects/{subject_id}/materials"),
            ("POST", "/api/research/subjects/{subject_id}/notes"),
            ("POST", "/api/research/subjects/{subject_id}/digests"),
            ("POST", "/api/research/subjects/{subject_id}/reviews"),
            ("GET", "/api/research/match-brief"),
            ("GET", "/api/project-center/overview"),
            ("GET", "/api/project-center/modules"),
            ("GET", "/api/project-center/modules/{module_id}"),
            ("GET", "/api/project-center/change-basket"),
            ("POST", "/api/project-center/change-basket"),
            ("PATCH", "/api/project-center/change-basket/{item_id}"),
            ("GET", "/api/project-center/requests"),
            ("POST", "/api/project-center/requests"),
            ("GET", "/api/project-center/requests/{request_id}"),
            ("PATCH", "/api/project-center/requests/{request_id}"),
            ("GET", "/api/project-center/deliveries"),
            ("POST", "/api/project-center/deliveries"),
            ("GET", "/api/project-center/deliveries/{delivery_id}"),
            ("PATCH", "/api/project-center/deliveries/{delivery_id}"),
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
