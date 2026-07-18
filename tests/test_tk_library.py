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
    def test_rag_search_and_reindex_default_to_current_tk_not_archive(self) -> None:
        from xiaoxue_api.modules.tk_knowledge import repository

        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"results": []}
        with mock.patch.object(repository.requests, "post", return_value=response) as post:
            repository.search_rag("BLG 纪律性", 12)
            repository.request_reindex()

        search_call, reindex_call = post.call_args_list
        self.assertEqual(search_call.kwargs["json"], {
            "query": "BLG 纪律性",
            "top": 12,
            "source": repository.CURRENT_TK_SOURCE,
        })
        self.assertEqual(reindex_call.kwargs["json"], {
            "force": False,
            "source_only": repository.CURRENT_TK_SOURCE,
        })

    def test_library_sorts_newest_first_and_paginates_without_losing_total(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.tk_knowledge import repository

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
        from xiaoxue_api.modules.tk_knowledge import repository

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
        from xiaoxue_api.modules.tk_knowledge import repository

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
        from xiaoxue_api.modules.tk_knowledge import repository

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tk(root, "short.md", "2026-07-14", "【结论】优势局先处理边线，再接资源团。")
            with mock.patch.object(repository, "TK_DIR", str(root)):
                with TestClient(main.app) as client:
                    payload = client.get("/api/tk/library?period=all&limit=30").json()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["filename"], "short.md")

    def test_entry_rejects_unsafe_or_non_markdown_filenames(self) -> None:
        import main
        from fastapi.testclient import TestClient
        from xiaoxue_api.modules.tk_knowledge import repository

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(repository, "TK_DIR", directory):
                with TestClient(main.app) as client:
                    response = client.get("/api/tk/entry/not-markdown.txt")

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
