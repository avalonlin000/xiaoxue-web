from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class WorkflowConfigTests(unittest.TestCase):
    def test_daily_artifacts_are_built_from_config(self) -> None:
        from workflow_contracts import build_daily_content_files, load_workflow_config

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "workflows.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema": "xiaoxue-workflows-v1",
                        "daily_content": {
                            "allowed_roots": [str(root)],
                            "artifacts": [
                                {
                                    "id": "daily_report",
                                    "title": "LOL电竞日报 {date}",
                                    "kind": "daily_report",
                                    "path": str(root / "LOL电竞日报_{date}.md"),
                                }
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_workflow_config(config_path)
            files = build_daily_content_files(config, "2026-07-12")

        self.assertEqual(list(files), ["daily_report"])
        self.assertEqual(files["daily_report"]["title"], "LOL电竞日报 2026-07-12")
        self.assertTrue(files["daily_report"]["path"].endswith("LOL电竞日报_2026-07-12.md"))

    def test_daily_artifact_cannot_escape_allowed_roots(self) -> None:
        from workflow_contracts import build_daily_content_files

        config = {
            "daily_content": {
                "allowed_roots": ["/safe/root"],
                "artifacts": [
                    {
                        "id": "unsafe",
                        "title": "unsafe",
                        "kind": "unsafe",
                        "path": "/tmp/{date}.md",
                    }
                ],
            }
        }

        with self.assertRaisesRegex(ValueError, "escapes allowed roots"):
            build_daily_content_files(config, "2026-07-12")

    def test_team_alias_lookup_is_config_driven_and_case_insensitive(self) -> None:
        from workflow_contracts import build_team_alias_lookup

        config = {
            "team_aliases": {
                "HLE": ["HLE", "Hanwha Life Esports", "韩华生命"],
                "GEN": ["GEN", "Gen.G", "三星"],
            }
        }

        aliases = build_team_alias_lookup(config)

        self.assertEqual(aliases["hanwha life esports"], "HLE")
        self.assertEqual(aliases["gen.g"], "GEN")
        self.assertEqual(aliases["三星"], "GEN")

    def test_repository_config_defines_current_artifacts_and_market_results(self) -> None:
        from workflow_contracts import load_workflow_config

        config = load_workflow_config(ROOT / "config" / "workflows.json")

        artifact_ids = [item["id"] for item in config["daily_content"]["artifacts"]]
        self.assertEqual(
            artifact_ids,
            ["daily_report"],
        )
        self.assertEqual(config["market"]["results"], ["未结算", "赢", "输", "走水", "放弃"])


class MainWorkflowIntegrationTests(unittest.TestCase):
    def test_daily_content_marks_a_day_without_matches_as_rest_day(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.daily_content import repository, service

        with tempfile.TemporaryDirectory() as directory:
            missing_path = str(Path(directory) / "missing-report.md")
            files = {
                "daily_report": {
                    "title": "LOL电竞日报 2026-07-13",
                    "kind": "daily_report",
                    "path": missing_path,
                }
            }
            config = {"daily_content": {"allowed_roots": [directory], "artifacts": [
                {"id": key, **meta} for key, meta in files.items()
            ]}}
            with mock.patch.object(repository, "load_config", return_value=config), mock.patch.object(
                service, "list_schedules", return_value=[]
            ):
                with TestClient(main.app) as client:
                    payload = client.get("/api/daily-content?date=2026-07-13").json()

        self.assertEqual(payload["day_state"], "no_matches")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["matches"], [])

    def test_daily_content_marks_missing_artifacts_only_when_matches_exist(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.daily_content import repository, service

        with tempfile.TemporaryDirectory() as directory:
            missing_path = str(Path(directory) / "missing-report.md")
            files = {
                "daily_report": {
                    "title": "LOL电竞日报 2026-07-14",
                    "kind": "daily_report",
                    "path": missing_path,
                }
            }
            matches = [{"date": "2026-07-14", "time": "17:00", "team_a": "A", "team_b": "B", "stage": "S16全球总决赛"}]
            config = {"daily_content": {"allowed_roots": [directory], "artifacts": [
                {"id": key, **meta} for key, meta in files.items()
            ]}}
            with mock.patch.object(repository, "load_config", return_value=config), mock.patch.object(
                service, "list_schedules", return_value=matches
            ):
                with TestClient(main.app) as client:
                    payload = client.get("/api/daily-content?date=2026-07-14").json()

        self.assertEqual(payload["day_state"], "content_missing")
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matches"], matches)

    def test_modules_use_isolated_workflow_contracts(self) -> None:
        from xiaoxue_api.modules.daily_content.public import resolve_date

        self.assertEqual(resolve_date("2026-07-12"), "2026-07-12")

    def test_lineup_prepare_endpoint_exposes_contract(self) -> None:
        import main
        from fastapi.testclient import TestClient

        lineup = {"TOP": "A", "JUNGLE": "B", "MID": "C", "BOT": "D", "SUPPORT": "E"}
        with TestClient(main.app) as client:
            response = client.post(
                "/api/lineup-workflow/prepare",
                json={
                    "match_name": "T1 vs GEN",
                    "blue_team": "T1",
                    "red_team": "GEN",
                    "blue_lineup": lineup,
                    "red_lineup": lineup,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])

    def test_health_reports_data_readiness_manifest(self) -> None:
        import main  # noqa: F401  确保应用已装配，health 才能读到模块状态
        from xiaoxue_api.modules.platform.public import health

        payload = health()

        self.assertIn("data_readiness", payload["checks"])
        self.assertIn("ok", payload["checks"]["data_readiness"])

    def test_health_does_not_treat_check_only_manifest_as_production_ready(self) -> None:
        import main  # noqa: F401  确保应用已装配，health 才能读到模块状态
        from xiaoxue_api.modules.platform.public import health
        from datetime import datetime

        with tempfile.TemporaryDirectory() as directory:
            date_str = datetime.now().strftime("%Y-%m-%d")
            path = Path(directory) / f"data_readiness_manifest_{date_str}.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "xiaoxue-data-readiness-run-v1",
                        "created_at": f"{date_str}T06:00:00",
                        "ok": True,
                        "mode": "check-only",
                        "stages": [
                            {"id": "scoregg_refresh", "status": "skipped"},
                            {"id": "ts_update", "status": "skipped"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"XIAOXUE_READINESS_ROOT": directory}):
                payload = health()

        self.assertFalse(payload["checks"]["data_readiness"]["ok"])
        self.assertEqual(payload["checks"]["data_readiness"]["status"], "diagnostic_only")

    def test_health_rejects_malformed_readiness_stages_without_crashing(self) -> None:
        import main  # noqa: F401  确保应用已装配，health 才能读到模块状态
        from xiaoxue_api.modules.platform.public import health
        from datetime import datetime

        with tempfile.TemporaryDirectory() as directory:
            date_str = datetime.now().strftime("%Y-%m-%d")
            path = Path(directory) / f"data_readiness_manifest_{date_str}.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "xiaoxue-data-readiness-run-v1",
                        "created_at": f"{date_str}T06:00:00",
                        "ok": True,
                        "mode": "full",
                        "stages": [
                            {"id": "scoregg_refresh", "status": "ok", "exit_code": "bad"},
                            "invalid-stage",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"XIAOXUE_READINESS_ROOT": directory}):
                payload = health()

        self.assertFalse(payload["checks"]["data_readiness"]["ok"])
        self.assertEqual(payload["checks"]["data_readiness"]["status"], "missing_or_blocked")

    def test_readiness_before_due_is_waiting_not_failure(self) -> None:
        from xiaoxue_api.modules.platform import repository as platform_repository
        from datetime import datetime, timedelta

        now = datetime.now()
        due = (now + timedelta(minutes=10)).strftime("%H:%M")
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"XIAOXUE_READINESS_ROOT": directory, "XIAOXUE_READINESS_DUE": due}
        ):
            readiness = platform_repository.readiness_check()

        self.assertFalse(readiness["ok"])
        self.assertEqual(readiness["state"], "not_due")
        self.assertIn("05:30", readiness["message"])
        self.assertTrue(readiness["due_at"])

    def test_readiness_after_due_counts_as_failure(self) -> None:
        from xiaoxue_api.modules.platform import repository as platform_repository
        from datetime import datetime, timedelta

        now = datetime.now()
        past = now - timedelta(minutes=5)
        due = "00:00" if past.date() != now.date() else past.strftime("%H:%M")
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"XIAOXUE_READINESS_ROOT": directory, "XIAOXUE_READINESS_DUE": due}
        ):
            readiness = platform_repository.readiness_check()

        self.assertEqual(readiness["state"], "failed")
        self.assertEqual(readiness["status"], "missing_or_blocked")

    def test_daily_module_waits_instead_of_reporting_broken_before_due(self) -> None:
        from xiaoxue_api.modules.platform import service as platform_service
        from xiaoxue_api.modules.daily_content.manifest import MODULE

        waiting = {"ok": False, "state": "not_due", "status": "not_due", "message": "今日数据尚未生成：每天 05:30 自动刷新，05:45 前属正常等待"}
        with mock.patch.object(
            platform_service.repository, "collect_checks", return_value={"data_readiness": waiting}
        ), mock.patch.object(
            platform_service, "_boot_status", {"daily_content": {"status": "ok", "manifest": MODULE}}
        ), mock.patch.object(
            platform_service, "get_operating_state", return_value={"state": "active", "message": ""}
        ):
            payload = platform_service.health()

        module = payload["modules"]["daily_content"]
        self.assertEqual(module["status"], "pending")
        self.assertEqual(module["reason_code"], "readiness_not_due")
        self.assertIn("05:30", module["message"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "healthy")

    def test_health_reports_user_paused_daily_as_disabled_not_broken(self) -> None:
        import main  # noqa: F401  确保应用已装配，health 才能读到模块状态
        from xiaoxue_api.modules.platform.public import health

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"XIAOXUE_READINESS_ROOT": directory}
        ), mock.patch(
            "xiaoxue_api.modules.platform.service.get_operating_state",
            return_value={"state": "paused_by_user", "message": "钧钧已主动暂停"},
        ):
            payload = health()

        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["modules"]["daily_content"]["status"], "disabled")
        self.assertIn("主动暂停", payload["modules"]["daily_content"]["message"])
        self.assertEqual(payload["modules"]["team"]["status"], "healthy")
        self.assertEqual(payload["modules"]["knowledge"]["status"], "healthy")


class LineupWorkflowTests(unittest.TestCase):
    def test_incomplete_lineup_returns_explicit_missing_fields(self) -> None:
        from workflow_contracts import prepare_lineup_workflow

        config = load_repo_config()
        result = prepare_lineup_workflow(
            {
                "match_name": "T1 vs GEN",
                "blue_team": "T1",
                "red_team": "GEN",
                "blue_lineup": {"TOP": "Gnar"},
                "red_lineup": {},
            },
            config,
        )

        self.assertFalse(result["ready"])
        self.assertIn("blue_lineup.JUNGLE", result["missing_fields"])
        self.assertIn("red_lineup.SUPPORT", result["missing_fields"])

    def test_complete_lineup_returns_eight_step_guarded_workflow(self) -> None:
        from workflow_contracts import prepare_lineup_workflow

        lineup = {"TOP": "A", "JUNGLE": "B", "MID": "C", "BOT": "D", "SUPPORT": "E"}
        result = prepare_lineup_workflow(
            {
                "match_name": "T1 vs GEN",
                "blue_team": "T1",
                "red_team": "GEN",
                "blue_lineup": lineup,
                "red_lineup": lineup,
                "market_context": "让分 -1.5",
                "pre_match_judgment": "赛前倾向 T1，但等待 BP",
            },
            load_repo_config(),
        )

        self.assertTrue(result["ready"])
        self.assertEqual(len(result["steps"]), 8)
        self.assertEqual(result["allowed_decisions"], ["保留", "降权", "取消", "等待"])
        self.assertIn("不得直接给买卖指令", result["guardrails"])


class MarketReviewWorkflowTests(unittest.TestCase):
    def test_review_preview_is_managed_and_never_auto_writes_knowledge(self) -> None:
        from workflow_contracts import build_market_note_review

        result = build_market_note_review(
            {"id": 7, "match_name": "T1 vs GEN", "review": "结果：未结算\n临场原始备注"},
            {
                "result": "赢",
                "actual_score": "2-1",
                "correct_points": "看对了中期资源团",
                "wrong_points": "低估前期换线",
                "missing_evidence": "缺首发确认",
                "calibration": "下次首发未确认时降权",
                "destinations": ["market_notes", "team_trading_note"],
            },
            load_repo_config(),
        )

        self.assertFalse(result["knowledge_write_allowed"])
        self.assertIn("XIAOXUE_REVIEW_START", result["review_text"])
        self.assertIn("结果：赢", result["review_text"])
        self.assertIn("临场原始备注", result["review_text"])


def load_repo_config() -> dict:
    from workflow_contracts import load_workflow_config

    return load_workflow_config(ROOT / "config" / "workflows.json")


if __name__ == "__main__":
    unittest.main()
