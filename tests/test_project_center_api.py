import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

import main


class ProjectCenterApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_path = os.environ.get("XIAOXUE_PROJECT_CENTER_DB_PATH")
        os.environ["XIAOXUE_PROJECT_CENTER_DB_PATH"] = str(Path(self.directory.name) / "project-center.sqlite3")
        self.client = TestClient(main.app)

    def tearDown(self):
        if self.previous_path is None:
            os.environ.pop("XIAOXUE_PROJECT_CENTER_DB_PATH", None)
        else:
            os.environ["XIAOXUE_PROJECT_CENTER_DB_PATH"] = self.previous_path
        self.directory.cleanup()

    def test_healthy_backends_do_not_promote_partial_contracts(self):
        from xiaoxue_api.modules.project_center import service

        self.assertEqual(service._module_runtime(["healthy"], "partial")["status"], "degraded")
        self.assertEqual(service._module_runtime(["healthy"], "available")["status"], "healthy")
        self.assertEqual(service._module_runtime(["broken"], "partial")["status"], "broken")
        self.assertEqual(service._module_runtime(["paused"], "available")["status"], "paused")

    def test_tree_names_affected_capabilities_without_claiming_whole_module_works(self):
        from xiaoxue_api.core.product_modules import module_catalog

        modules = {name: {"status": "healthy"} for item in module_catalog()
                   for name in item["compatibility"]["backend_capabilities"]}
        modules["daily_content"] = {"status": "broken", "reason_code": "readiness_missing"}
        with patch("xiaoxue_api.modules.project_center.service._safe_health", return_value={"modules": modules}):
            data = self.client.get("/api/project-center/modules").json()["data"]
        tree = {item["id"]: item for item in data["tree"]}
        self.assertEqual(tree["methods-and-judgment"]["runtime"]["status"], "degraded")
        daily = tree["daily-and-automation"]
        self.assertEqual(daily["runtime"]["label"], "需要处理")
        self.assertTrue(any("当天数据就绪信息缺失" in item["reason"] for item in daily["runtime_details"]))
        self.assertIn("状态可读取不等于日报已生成", daily["current_capability"])

    def test_objects_explain_usable_scope_limits_entry_and_next_step(self):
        objects = self.client.get("/api/project-center/modules").json()["data"]["object_catalog"]["objects"]
        for name, item in objects.items():
            for field in ("current_capability", "limitations", "entry", "next_step", "known_gaps"):
                self.assertTrue(item[field], f"{name}: {field}")
        self.assertIn("还没有正式足球业务入口", objects["football"]["limitations"])
        self.assertIn("历史赔率", objects["valorant"]["limitations"])

    def test_overview_and_modules_keep_content_runtime_and_progress_separate(self):
        overview = self.client.get("/api/project-center/overview")
        modules = self.client.get("/api/project-center/modules")

        self.assertEqual(overview.status_code, 200)
        data = overview.json()["data"]
        self.assertIn("project", data)
        self.assertIn("runtime", data)
        self.assertIn("current_deliveries", data)
        self.assertIn("source", data)
        self.assertIn("observed_at", data)
        self.assertIn("content_version", data)
        self.assertEqual(data["object_catalog"]["contract"], "shared-object-package-v1")
        self.assertIn("football", data["object_catalog"]["objects"])
        self.assertFalse(data["stale"])
        self.assertEqual(modules.status_code, 200)
        module_items = modules.json()["data"]["items"]
        self.assertEqual(modules.json()["data"]["object_catalog"]["objects"]["cs2"]["status"], "partial")
        self.assertEqual(len(module_items), len({item["name"] for item in module_items}))
        team_material = next(item for item in module_items if item["name"] == "队伍资料")
        self.assertEqual(team_material["ability_ids"], ["ts_strength", "team_profile"])
        current_match = next(item for item in module_items if item["id"] == "current_match")
        self.assertEqual(current_match["entry"]["type"], "web")
        self.assertEqual(current_match["entry"]["page"], "event")
        self.assertNotIn("/api/", str(current_match))
        tree = modules.json()["data"]["tree"]
        self.assertEqual(len(tree), 8)
        self.assertEqual(tree[0]["name"], "日报与自动化")
        self.assertEqual(tree[-1]["name"], "小雪对话能力与固定边界")
        self.assertTrue(tree[0]["children"])
        self.assertIn("engineering_details", tree[0])
        self.assertNotIn("/api/", str(tree))

    def test_basket_discussion_request_delivery_and_feedback_round_trip(self):
        created = self.client.post("/api/project-center/change-basket", json={
            "module_id": "current_match", "optional_note": "这里切换比赛时我想更快看清下一步", "idempotency_key": "basket-round-trip",
        })
        self.assertEqual(created.status_code, 200)
        item = created.json()["data"]["item"]
        self.assertEqual(item["status"], "pending")
        self.assertTrue(item["is_focus"])

        duplicate = self.client.post("/api/project-center/change-basket", json={
            "module_id": "current_match", "optional_note": "这里切换比赛时我想更快看清下一步", "idempotency_key": "basket-round-trip",
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["data"]["deduplicated"])
        self.assertEqual(duplicate.json()["data"]["item"]["id"], item["id"])

        repeated_module = self.client.post("/api/project-center/change-basket", json={
            "module_id": "current_match", "optional_note": "又点了一次同一块", "idempotency_key": "basket-round-trip-again",
        })
        self.assertEqual(repeated_module.status_code, 200)
        self.assertTrue(repeated_module.json()["data"]["deduplicated"])
        self.assertEqual(repeated_module.json()["data"]["item"]["id"], item["id"])
        self.assertEqual(self.client.get("/api/project-center/change-basket").json()["data"]["count"], 1)

        paused = self.client.patch(f"/api/project-center/change-basket/{item['id']}", json={
            "revision": item["revision"], "status": "paused",
        })
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["data"]["item"]["status"], "paused")
        resumed_item = paused.json()["data"]["item"]
        resumed = self.client.patch(f"/api/project-center/change-basket/{item['id']}", json={
            "revision": resumed_item["revision"], "status": "pending", "is_focus": True,
        })
        self.assertEqual(resumed.status_code, 200)
        item = resumed.json()["data"]["item"]

        request = self.client.post("/api/project-center/requests", json={
            "basket_item_ids": [item["id"]],
            "user_problem": "切换单场后，我希望下一步一眼看清。",
            "desired_experience": "我能自然接着讨论，而不是重新找入口。",
            "desired_result": "当前赛事页更清楚地展示当前焦点和下一步。",
            "discussion_confirmed": True,
            "idempotency_key": "request-round-trip",
        })
        self.assertEqual(request.status_code, 200)
        request_item = request.json()["data"]["item"]
        self.assertEqual(request_item["status"], "Planned")
        self.assertEqual(self.client.get("/api/project-center/change-basket").json()["data"]["count"], 0)

        delivery = self.client.post("/api/project-center/deliveries", json={
            "request_id": request_item["id"],
            "title": "当前赛事焦点阅读优化",
            "status": "Released",
            "user_visible_change": "进入当前赛事后可以先看到当前焦点和接下来能做什么。",
            "user_validation_path": "当前赛事页",
            "verification_evidence": [{
                "observed_at": "2026-08-18T10:00:00+00:00",
                "environment": "本地工作台",
                "entry": "当前赛事页",
                "result": "焦点和下一步已显示",
                "risk": "无",
            }],
            "idempotency_key": "delivery-round-trip",
        })
        self.assertEqual(delivery.status_code, 200)
        delivery_item = delivery.json()["data"]["item"]
        feedback = self.client.patch(f"/api/project-center/deliveries/{delivery_item['id']}", json={
            "revision": delivery_item["revision"], "feedback_action": "return_to_basket", "feedback_note": "还想换一种阅读方式",
        })
        self.assertEqual(feedback.status_code, 200)
        self.assertEqual(feedback.json()["data"]["item"]["status"], "Abandoned")
        returned = self.client.get("/api/project-center/change-basket").json()["data"]
        self.assertEqual(returned["count"], 1)
        self.assertIn("换一种阅读方式", returned["items"][0]["optional_note"])

    def test_invalid_unclassified_empty_input_does_not_create_store(self):
        response = self.client.post("/api/project-center/change-basket", json={"optional_note": ""})

        self.assertEqual(response.status_code, 400)
        self.assertIn("至少留下一句", str(response.json()))
        self.assertFalse((Path(self.directory.name) / "project-center.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
