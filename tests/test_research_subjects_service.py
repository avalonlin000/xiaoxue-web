import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from xiaoxue_api.modules.match.archive import service


class ResearchSubjectsServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_path = os.environ.get("XIAOXUE_RESEARCH_CORE_DB_PATH")
        os.environ["XIAOXUE_RESEARCH_CORE_DB_PATH"] = str(Path(self.directory.name) / "research.sqlite3")

    def tearDown(self):
        if self.previous_path is None:
            os.environ.pop("XIAOXUE_RESEARCH_CORE_DB_PATH", None)
        else:
            os.environ["XIAOXUE_RESEARCH_CORE_DB_PATH"] = self.previous_path
        self.directory.cleanup()

    def test_subject_material_and_note_persist_across_service_calls(self):
        subject = service.open_subject({"domain": "lol", "subject_key": "BLG", "name": "Bilibili Gaming"})
        service.create_material(subject["id"], {
            "kind": "news",
            "content": "BLG 公布本场首发。",
            "captured_at": "2026-08-01T08:05:00+00:00",
            "source_name": "官方公告",
            "source_url": "",
            "event_id": None,
        })
        service.create_user_note(subject["id"], {"content": "我觉得这场中期要重点观察。", "kind": "user_note", "event_id": None})

        dossier = service.get_dossier(subject["id"])

        self.assertEqual(dossier["subject"]["subject_key"], "BLG")
        self.assertEqual(dossier["raw_materials"][0]["source_name"], "官方公告")
        self.assertEqual(dossier["user_notes"][0]["content"], "我觉得这场中期要重点观察。")

    def test_other_domains_are_not_accepted_before_their_adapter_exists(self):
        with self.assertRaisesRegex(ValueError, "只支持 LOL"):
            service.open_subject({"domain": "stock", "subject_key": "AAPL", "name": "Apple"})

    def test_match_brief_joins_existing_facts_and_market_records_without_creating_an_archive(self):
        archive_path = Path(self.directory.name) / "research.sqlite3"
        desk = {
            "match": {"game": "lol", "team_a": "BLG", "team_b": "T1", "event": "MSI", "match_date": "2026-08-04", "match_time": "18:00", "match_format": "BO3"},
            "team_a": {"starters": []}, "team_b": {"starters": []}, "trading_notes": {},
        }
        with mock.patch.object(service, "get_match_desk", return_value=desk):
            brief = service.get_match_research_brief({"team_a": "BLG", "team_b": "T1"})

        self.assertEqual(brief["match_facts"], desk)
        self.assertEqual(brief["market_records"], [])
        self.assertEqual(brief["team_archives"], [])
        self.assertFalse(archive_path.exists())


if __name__ == "__main__":
    unittest.main()
