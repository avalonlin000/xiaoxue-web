from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def write_tk(root: Path, filename: str, created: str, body: str, *, team: str = "", source: str = "测试来源") -> None:
    root.joinpath(filename).write_text(
        "\n".join(
            [
                "---",
                f"created: {created}",
                f"source: {source}",
                f"team: {team}",
                "tags: [BP, 版本理解]",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )


class TkLibraryTests(unittest.TestCase):
    def test_mempalace_search_and_reindex_default_to_current_tk_not_archive(self) -> None:
        from xiaoxue_api.modules.knowledge.tk import repository

        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"results": []}
        with mock.patch.object(repository.requests, "post", return_value=response) as post:
            repository.search_rag("BLG 纪律性", 12)
            repository.request_reindex()

        search_call, reindex_call = post.call_args_list
        self.assertEqual(search_call.args[0], repository.MEMPALACE_API)
        self.assertEqual(search_call.kwargs["json"], {
            "query": "BLG 纪律性",
            "top": 12,
            "source": repository.CURRENT_TK_SOURCE,
        })
        self.assertEqual(reindex_call.args[0], repository.MEMPALACE_REINDEX_API)
        self.assertEqual(reindex_call.kwargs["json"], {
            "force": False,
            "source_only": repository.CURRENT_TK_SOURCE,
        })


    def test_library_sorts_newest_first_and_paginates_without_losing_total(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = "【结论】" + "完整战术内容。" * 30
            write_tk(root, "old.md", "2026-06-10", body)
            write_tk(root, "newest.md", "2026-07-14", body)
            write_tk(root, "middle.md", "2026-07-09", body)
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    payload = client.get("/api/tk/library?period=all&offset=0&limit=2").json()

        self.assertEqual([item["filename"] for item in payload["results"]], ["newest.md", "middle.md"])
        self.assertEqual(payload["total"], 3)
        self.assertTrue(payload["has_more"])
        self.assertEqual(payload["available_months"], ["2026-07", "2026-06"])

    def test_library_filters_by_month_keyword_and_team(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tk(root, "t1-july.md", "2026-07-12", "【结论】T1 围绕中路做资源团。" * 12, team="T1")
            write_tk(root, "blg-july.md", "2026-07-11", "【结论】BLG 通过下路取得线权。" * 12, team="BLG")
            write_tk(root, "t1-june.md", "2026-06-30", "【结论】T1 六月版本理解。" * 12, team="T1")
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    payload = client.get(
                        "/api/tk/library?period=month&month=2026-07&q=资源团&team=T1&limit=30"
                    ).json()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["filename"], "t1-july.md")

    def test_entry_returns_the_complete_body_instead_of_an_800_character_slice(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = "【结论】长文必须完整显示。\n\n" + "战术推演与边界。" * 180
            write_tk(root, "long-entry.md", "2026-07-14", body)
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    response = client.get("/api/tk/entry/long-entry.md")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], body)
        self.assertGreater(len(response.json()["content"]), 800)

    def test_library_keeps_short_but_meaningful_tk_entries(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tk(root, "short.md", "2026-07-14", "【结论】优势局先处理边线，再接资源团。")
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    payload = client.get("/api/tk/library?period=all&limit=30").json()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["filename"], "short.md")

    def test_library_hides_pointer_files_and_strips_technical_blocks_from_readable_tk(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tk(root, "pointer.md", "2026-07-14", "@/tmp/BV1example_tk.txt")
            write_tk(root, "readable.md", "2026-07-14", "【结论】保留这条战术判断。\n```yaml\ninternal: should-not-show\n```\n- 证据：/home/ubuntu/internal.md\n【推演】后续继续观察。")
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    library = client.get("/api/tk/library?period=all&limit=30").json()
                    entry = client.get("/api/tk/entry/readable.md").json()
                    hidden_search = client.get("/api/tk/library?period=all&q=/home/ubuntu&limit=30").json()

        self.assertEqual(library["total"], 1)
        self.assertEqual(library["results"][0]["filename"], "readable.md")
        self.assertIn("保留这条战术判断", entry["content"])
        self.assertIn("后续继续观察", entry["content"])
        self.assertNotIn("internal:", entry["content"])
        self.assertNotIn("/home/ubuntu", entry["content"])
        self.assertEqual(hidden_search["total"], 0)

    def test_personal_write_strips_technical_fragments_before_persistence(self) -> None:
        from xiaoxue_api.modules.knowledge.tk import repository, service

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(repository, "TK_DIR", directory), mock.patch.object(repository, "request_reindex", return_value=True):
            created = service.create({"content": "【结论】保留正常判断。\n```json\n{\"debug\": true}\n```\n/tmp/ignore-me"})
            raw = repository.read_document(created["filename"])["content"]

        self.assertIn("保留正常判断", raw)
        self.assertNotIn("debug", raw)
        self.assertNotIn("/tmp/ignore-me", raw)

    def test_personal_remember_writes_raw_words_without_metadata_or_overwrite(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository, service

        teams = [
            {"short_name": "BLG", "name": "Bilibili Gaming", "team_id": "blg"},
            {"short_name": "T1", "name": "T1", "team_id": "t1"},
        ]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(repository, "TK_DIR", directory), mock.patch.object(service, "list_teams", return_value=teams):
            with TestClient(main.app) as client:
                first = client.post("/api/tk/remember", json={"text": "BLG 对 T1 这场先不碰，观察前十五分钟。"}).json()
                second = client.post("/api/tk/remember", json={"text": "BLG 对 T1 这场先不碰，观察前十五分钟。"}).json()
                entry = client.get(f"/api/tk/entry/{first['filename']}").json()
                raw = repository.read_document(first["filename"])["content"]

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(first["filename"], second["filename"])
        self.assertEqual(first["source"], "钧钧口述")
        self.assertEqual(first["teams"], ["BLG", "T1"])
        self.assertEqual(entry["content"], "BLG 对 T1 这场先不碰，观察前十五分钟。")
        self.assertIn("队伍:BLG", raw)
        self.assertIn("队伍:T1", raw)

    def test_entry_rejects_unsafe_or_non_markdown_filenames(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(repository, "TK_DIR", directory):
                with TestClient(main.app) as client:
                    response = client.get("/api/tk/entry/not-markdown.txt")

        self.assertEqual(response.status_code, 400)

    def test_delete_removes_the_selected_tk_and_the_entry_cannot_be_read_back(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.knowledge.tk import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tk(root, "remove-me.md", "2026-07-14", "【结论】这是一条用于删除验收的临时 TK。")
            with mock.patch.object(repository, "TK_DIR", directory), mock.patch.object(repository, "request_reindex", return_value=True):
                with TestClient(main.app) as client:
                    deleted = client.delete("/api/tk/remove-me.md")
                    readback = client.get("/api/tk/entry/remove-me.md")

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"ok": True})
        self.assertEqual(readback.status_code, 404)


if __name__ == "__main__":
    unittest.main()
