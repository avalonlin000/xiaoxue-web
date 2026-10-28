from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from xiaoxue_api.modules.match.event import public as current_event_public
from xiaoxue_api.modules.daily_content import repository, service


class DailyPublicationStateTests(unittest.TestCase):
    def test_project_center_retains_the_actual_readable_daily_receipt(self):
        from xiaoxue_api.modules.platform.center import service as project_service
        with mock.patch.object(project_service, "get_daily_content", return_value={"day_state": "ready", "report": {"publication_status": "verified", "url": "https://example.feishu.cn/docx/fixture", "snapshot_at": "2026-10-19T07:00:00+08:00"}}):
            result = project_service._daily_summary()
        self.assertEqual(result["report"]["url"], "https://example.feishu.cn/docx/fixture")
        self.assertEqual(result["report"]["publication_status"], "verified")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.date = "2026-10-19"
        self.report_path = self.root / f"LOL电竞日报_{self.date}.md"
        self.report_path.write_text("# LOL电竞日报\n\n已经核实的阅读成果。", encoding="utf-8")
        self.manifest_path = self.root / f"daily_run_manifest_{self.date}.json"
        self.config = {"daily_content": {
            "operating_state": "paused_by_user",
            "operating_message": "已主动暂停",
            "allowed_roots": [str(self.root)],
            "artifacts": [
                {"id": "daily_report", "title": "日报 {date}", "kind": "daily_report",
                 "path": str(self.root / "LOL电竞日报_{date}.md")},
                {"id": "trading_report", "title": "旧交易日报", "kind": "trading_report",
                 "path": str(self.root / "不存在的交易日报_{date}.md")},
            ],
        }}
        self.manifest = {
            "schema": "xiaoxue-daily-run-manifest-v2", "date": self.date,
            "created_at": "2026-10-19 07:01:05", "run_id": "daily-fixture",
            "audit_ok": True, "validation_errors": [], "published": True,
            "artifacts": {self.report_path.name: hashlib.sha256(self.report_path.read_bytes()).hexdigest()},
            "destinations": {
                "scripts": {"status": "verified", "matches_source": True},
                "wiki": {"status": "verified", "matches_source": True},
                "feishu": {"status": "verified", "url": "https://example.feishu.cn/docx/fixture",
                           "part_count": 1, "parts": [{"status": "verified"}]},
            },
        }
        self.write_manifest()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(repository, "load_config", return_value=self.config))
        self.schedules = self.stack.enter_context(mock.patch.object(
            service, "list_schedules", return_value=[{"date": self.date, "team_a": "A", "team_b": "B", "league": "S16全球总决赛", "stage": "S16全球总决赛"}]
        ))
        self.materials = self.stack.enter_context(mock.patch.object(
            current_event_public, "list_prepared_materials", create=True,
            return_value={"date": self.date, "items": [{"match_id": "fixture-match", "revision_id": "r1"}]},
        ))

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_verified_publication_has_direct_reader_url_and_snapshot(self):
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "ready")
        report = result["report"]
        self.assertEqual(report["publication_status"], "verified")
        self.assertEqual(report["run_id"], "daily-fixture")
        self.assertEqual(report["date"], self.date)
        self.assertEqual(report["snapshot_at"], "2026-10-19 07:01:05")
        self.assertTrue(report["published"])
        self.assertEqual(report["url"], "https://example.feishu.cn/docx/fixture")
        self.assertTrue(report["verification"]["artifact_matches"])
        self.assertEqual(result["latest_matches"][0]["revision_id"], "r1")
        self.materials.assert_called_once_with(self.date, limit=200)

    def test_existing_markdown_without_manifest_is_not_ready(self):
        self.manifest_path.unlink()
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "content_missing")
        self.assertEqual(result["report"]["publication_status"], "missing")
        self.assertFalse(result["report"]["published"])

    def test_legacy_trading_report_is_not_required(self):
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "ready")
        self.assertFalse(next(item for item in result["items"] if item["kind"] == "trading_report")["required"])

    def test_verified_report_remains_readable_on_rest_day(self):
        self.schedules.return_value = []
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "ready")
        self.assertEqual(result["match_count"], 0)
        self.assertTrue(result["report"]["url"])

    def test_paused_configuration_and_observed_publication_are_not_conflated(self):
        result = service.get_daily_content(self.date)
        self.assertEqual(result["operating_state"]["state"], "paused_by_user")
        self.assertEqual(result["operating_state"]["observed_publication_status"], "verified")
        self.assertTrue(result["operating_state"]["state_difference"])
        self.assertEqual(self.config["daily_content"]["operating_state"], "paused_by_user")

    def test_failed_destination_cannot_be_promoted_by_published_flag(self):
        self.manifest["destinations"]["feishu"]["parts"][0]["status"] = "failed"
        self.write_manifest()
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "content_missing")
        self.assertEqual(result["report"]["publication_status"], "unverified")
        self.assertTrue(result["report"]["published"])

    def test_missing_publication_part_cannot_be_marked_verified(self):
        self.manifest["destinations"]["feishu"]["part_count"] = 2
        self.write_manifest()
        self.assertEqual(service.get_daily_content(self.date)["report"]["publication_status"], "unverified")

    def test_readiness_blocked_receipt_does_not_hide_available_materials(self):
        self.manifest.update({"published": False, "audit_ok": False,
                              "mode": "blocked-by-data-readiness", "destinations": {},
                              "validation_errors": ["readiness missing"]})
        self.write_manifest()
        result = service.get_daily_content(self.date)
        self.assertEqual(result["report"]["publication_status"], "blocked-by-data-readiness")
        self.assertEqual(result["latest_matches"][0]["match_id"], "fixture-match")

    def test_no_matches_receipt_is_a_complete_empty_outcome(self):
        self.schedules.return_value = []
        self.manifest.update({
            "run_id": "rest-day-fixture",
            "published": False,
            "audit_ok": True,
            "mode": "no_matches",
            "result": {
                "outcome": "no_matches",
                "message": "当日没有已确认的比赛，未生成或发布日报。",
                "today_match_count": 0,
            },
            "destinations": {},
            "validation_errors": [],
        })
        self.write_manifest()
        result = service.get_daily_content(self.date)
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["day_state"], "no_matches")
        self.assertEqual(result["report"]["publication_status"], "no_matches")
        self.assertFalse(result["report"]["published"])

    def test_material_failure_does_not_break_verified_report(self):
        self.materials.side_effect = RuntimeError("private internal detail")
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "ready")
        self.assertEqual(result["latest_matches"], [])
        self.assertEqual(result["latest_matches_status"], "unavailable")
        self.assertNotIn("private internal detail", json.dumps(result))

    def test_wrong_date_and_invalid_json_are_not_valid_receipts(self):
        self.manifest["date"] = "2026-10-18"
        self.write_manifest()
        self.assertEqual(service.get_daily_content(self.date)["report"]["publication_status"], "invalid")
        self.manifest_path.write_text("{broken", encoding="utf-8")
        self.assertEqual(service.get_daily_content(self.date)["report"]["publication_status"], "invalid")

    def test_malformed_receipt_mode_is_not_an_internal_error(self):
        self.manifest.update({"published": False, "mode": {"unexpected": "value"}})
        self.write_manifest()
        self.assertNotEqual(service.get_daily_content(self.date)["report"]["publication_status"], "verified")

    def test_missing_snapshot_identity_cannot_be_verified(self):
        self.manifest.pop("run_id")
        self.write_manifest()
        self.assertEqual(service.get_daily_content(self.date)["report"]["publication_status"], "unverified")

    def test_changed_local_markdown_does_not_match_frozen_publication(self):
        self.report_path.write_text("changed after publication", encoding="utf-8")
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "content_missing")
        self.assertFalse(result["report"]["verification"]["artifact_matches"])

    def test_non_web_reader_url_is_not_exposed_or_ready(self):
        self.manifest["destinations"]["feishu"]["url"] = "javascript:alert(1)"
        self.write_manifest()
        result = service.get_daily_content(self.date)
        self.assertEqual(result["day_state"], "content_missing")
        self.assertEqual(result["report"]["url"], "")

    def test_original_api_returns_verified_link_and_latest_materials_without_network(self):
        from fastapi.testclient import TestClient
        import main

        with TestClient(main.app) as client:
            response = client.get(f"/api/daily-content?date={self.date}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"]["publication_status"], "verified")
        self.assertEqual(response.json()["latest_matches"][0]["match_id"], "fixture-match")


if __name__ == "__main__":
    unittest.main()
