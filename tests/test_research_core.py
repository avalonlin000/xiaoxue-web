import sqlite3
import unittest

from xiaoxue_api.research_core import repository, service


class ResearchCoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        repository.initialize(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_subject_dossier_keeps_raw_materials_and_user_notes_separate(self):
        subject = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")
        event = service.record_event(
            self.connection, subject["id"], "match", "BLG vs T1", "2026-08-01T08:00:00+00:00"
        )
        material = service.record_material(
            self.connection,
            subject["id"],
            "news",
            "BLG 公布本场首发。",
            "2026-08-01T08:05:00+00:00",
            source_name="官方公告",
            event_id=event["id"],
        )
        note = service.record_user_note(
            self.connection, subject["id"], "我觉得 BLG 中期要重点观察。", event_id=event["id"]
        )

        dossier = service.get_subject_dossier(self.connection, subject["id"])

        self.assertEqual(dossier["subject"]["name"], "Bilibili Gaming")
        self.assertEqual(dossier["raw_materials"][0]["id"], material["id"])
        self.assertEqual(dossier["user_notes"][0]["id"], note["id"])
        self.assertEqual(dossier["materials_by_kind"]["news"][0]["content"], "BLG 公布本场首发。")
        self.assertEqual({entry["entry_type"] for entry in dossier["timeline"]}, {"event", "material", "note"})

    def test_opening_same_subject_reuses_its_dossier(self):
        original = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")
        reopened = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming（BLG）")

        self.assertEqual(reopened["id"], original["id"])
        self.assertEqual(reopened["name"], "Bilibili Gaming（BLG）")

    def test_subject_directory_finds_a_subject_by_name_or_key(self):
        first = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")
        service.open_subject(self.connection, "lol", "T1", "T1")

        found = service.list_subjects(self.connection, "bili")

        self.assertEqual([item["id"] for item in found], [first["id"]])

    def test_material_requires_a_traceable_source(self):
        subject = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")

        with self.assertRaisesRegex(ValueError, "来源名称或链接"):
            service.record_material(
                self.connection,
                subject["id"],
                "news",
                "未标来源的内容",
                "2026-08-01T08:05:00+00:00",
            )

    def test_digest_requires_owned_source_material_and_stays_separate(self):
        subject = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")
        material = service.record_material(self.connection, subject["id"], "news", "公布首发", "2026-08-01", source_name="官方公告")

        digest = service.record_digest(self.connection, subject["id"], "官方资料确认首发已公布。", source_material_ids=[material["id"]])
        dossier = service.get_subject_dossier(self.connection, subject["id"])

        self.assertEqual(dossier["organized_digests"][0]["id"], digest["id"])
        self.assertEqual(digest["source_material_ids"], [material["id"]])

    def test_material_cannot_attach_to_another_subjects_event(self):
        first = service.open_subject(self.connection, "lol", "BLG", "Bilibili Gaming")
        second = service.open_subject(self.connection, "lol", "T1", "T1")
        event = service.record_event(
            self.connection, first["id"], "match", "BLG vs T1", "2026-08-01T08:00:00+00:00"
        )

        with self.assertRaisesRegex(LookupError, "不属于当前主体"):
            service.record_material(
                self.connection,
                second["id"],
                "news",
                "公布首发",
                "2026-08-01T08:05:00+00:00",
                source_name="官方公告",
                event_id=event["id"],
            )


if __name__ == "__main__":
    unittest.main()
