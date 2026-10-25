import json
import os
import unittest
from unittest import mock

from xiaoxue_api.core import web_search
from xiaoxue_api.modules.match.event import collection_repository


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class LocalWebSearchTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {
            "XIAOXUE_SEARCH_URL": "http://127.0.0.1:8338/searxng/search",
            "XIAOXUE_SEARCH_HEALTH_URL": "http://127.0.0.1:8338/__admin/health",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_search_normalizes_deduplicates_and_bounds_results(self):
        payload = {
            "results": [
                {"title": "TES vs G2 赛前预测", "url": "https://example.com/tes-g2",
                 "content": "  TES  赛前消息 ", "engine": "parallel_mcp"},
                {"title": "重复链接", "url": "https://example.com/tes-g2", "content": "重复"},
                {"title": "赔率文章", "url": "https://example.com/odds", "content": "赔率分析",
                 "publishedDate": "2026-10-25"},
                {"title": "坏链接", "url": "ftp://example.com/file"},
            ]
        }
        with mock.patch.object(web_search, "urlopen", return_value=_FakeResponse(payload)):
            rows = web_search.search_web("TES G2 赛前预测", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "TES vs G2 赛前预测")
        self.assertEqual(rows[0]["snippet"], "TES 赛前消息")
        self.assertEqual(rows[1]["published_at"], "2026-10-25")
        self.assertEqual(rows[0]["verification"], "search_lead")

    def test_payload_is_project_contract(self):
        payload = {"results": [{"title": "英雄联盟 S16", "url": "https://lol.qq.com/news",
                                "content": "赛程", "engines": ["bing"]}]}
        with mock.patch.object(web_search, "urlopen", return_value=_FakeResponse(payload)):
            result = web_search.search_web_payload("S16", limit=5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "local/searxng")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["engine"], "bing")

    def test_empty_and_invalid_payloads_are_empty_not_fabricated(self):
        with mock.patch.object(web_search, "urlopen", return_value=_FakeResponse({})):
            self.assertEqual(web_search.search_web("query"), [])
        with mock.patch.object(web_search, "urlopen", return_value=_FakeResponse({"results": "bad"})):
            self.assertEqual(web_search.search_web("query"), [])

    def test_health_reports_unavailable_instead_of_raising(self):
        with mock.patch.object(web_search, "urlopen", side_effect=OSError("refused")):
            result = web_search.search_service_health()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unavailable")

    def test_collection_search_prefers_local_service(self):
        self.assertEqual(collection_repository.SEARCH_PROVIDERS[0][0], "local/searxng")


if __name__ == "__main__":
    unittest.main()
