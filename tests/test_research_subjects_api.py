import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main


class ResearchSubjectsApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_path = os.environ.get("XIAOXUE_RESEARCH_CORE_DB_PATH")
        os.environ["XIAOXUE_RESEARCH_CORE_DB_PATH"] = str(Path(self.directory.name) / "research.sqlite3")
        self.client = TestClient(main.app)

    def tearDown(self):
        if self.previous_path is None:
            os.environ.pop("XIAOXUE_RESEARCH_CORE_DB_PATH", None)
        else:
            os.environ["XIAOXUE_RESEARCH_CORE_DB_PATH"] = self.previous_path
        self.directory.cleanup()

    def test_subject_dossier_round_trip(self):
        subject = self.client.post("/api/research/subjects", json={
            "domain": "lol", "subject_key": "BLG", "name": "Bilibili Gaming",
        })
        self.assertEqual(subject.status_code, 200)
        subject_id = subject.json()["id"]

        event = self.client.post(f"/api/research/subjects/{subject_id}/events", json={
            "kind": "match", "title": "BLG vs T1", "occurred_at": "2026-08-01T08:00:00+00:00", "details": "赛前资料整理",
        })
        self.assertEqual(event.status_code, 200)
        event_id = event.json()["id"]

        material = self.client.post(f"/api/research/subjects/{subject_id}/materials", json={
            "kind": "news",
            "content": "BLG 公布本场首发。",
            "captured_at": "2026-08-01T08:05:00+00:00",
            "source_name": "官方公告",
            "event_id": event_id,
        })
        digest = self.client.post(f"/api/research/subjects/{subject_id}/digests", json={
            "kind": "organized_fact",
            "content": "官方资料确认 BLG 本场首发已公布。",
            "event_id": event_id,
            "source_material_ids": [material.json()["id"]],
        })
        note = self.client.post(f"/api/research/subjects/{subject_id}/notes", json={
            "content": "我觉得 BLG 中期要重点观察。",
            "event_id": event_id,
        })
        review = self.client.post(f"/api/research/subjects/{subject_id}/reviews", json={
            "outcome": "赛后待核对",
            "review": "复盘时要对照首发与中期节奏是否兑现。",
            "event_id": event_id,
        })
        dossier = self.client.get(f"/api/research/subjects/{subject_id}")

        self.assertEqual(material.status_code, 200)
        self.assertEqual(digest.status_code, 200)
        self.assertEqual(note.status_code, 200)
        self.assertEqual(review.status_code, 200)
        self.assertEqual(dossier.status_code, 200)
        payload = dossier.json()
        self.assertEqual(payload["subject"]["subject_key"], "BLG")
        self.assertEqual(payload["events"][0]["title"], "BLG vs T1")
        self.assertEqual(payload["raw_materials"][0]["event_id"], event_id)
        self.assertEqual(payload["raw_materials"][0]["source_name"], "官方公告")
        self.assertEqual(payload["organized_digests"][0]["source_material_ids"], [material.json()["id"]])
        self.assertEqual(payload["user_notes"][0]["content"], "我觉得 BLG 中期要重点观察。")
        self.assertEqual(payload["reviews"][0]["outcome"], "赛后待核对")

        directory = self.client.get("/api/research/subjects", params={"query": "blg"})
        self.assertEqual(directory.status_code, 200)
        self.assertEqual(directory.json()["subjects"][0]["id"], subject_id)

    def test_reading_an_empty_archive_does_not_create_a_database_file(self):
        response = self.client.get("/api/research/subjects", params={"query": "BLG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"subjects": []})
        self.assertFalse((Path(self.directory.name) / "research.sqlite3").exists())

    def test_other_domain_is_a_clear_empty_boundary_not_a_hidden_future_feature(self):
        response = self.client.post("/api/research/subjects", json={
            "domain": "stock", "subject_key": "AAPL", "name": "Apple",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("只支持 LOL", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
