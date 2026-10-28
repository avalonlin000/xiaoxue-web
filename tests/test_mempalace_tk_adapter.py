from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from fastapi.testclient import TestClient


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mempalace_tk_api.py"
SPEC = importlib.util.spec_from_file_location("mempalace_tk_api_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_search_maps_mempalace_drawer_to_legacy_tk_shape():
    raw = {
        "text": "---\nsource: 中年电竞人\nsource_type: version_meta\ncreated: 2026-05-24\n---\n纪律性问题核心",
        "source_file": "version_meta_574_纪律性问题核心_决策思维错误.md",
        "similarity": 0.81,
        "created_at": "2026-07-19T12:00:00",
    }
    with patch.object(MODULE, "_embedding_readiness", return_value={"ready": True}), \
            patch.object(MODULE, "search_memories", return_value={"results": [raw]}) as search:
        with TestClient(MODULE.app) as client:
            response = client.post("/api/search", json={"query": "BLG 纪律性", "top": 3})

    assert response.status_code == 200
    assert search.call_args.kwargs["candidate_strategy"] == "union"
    assert response.json()["results"] == [{
        "id": "version_meta_574_纪律性问题核心_决策思维错误.md",
        "title": "version_meta_574_纪律性问题核心_决策思维错误.md",
        "text": raw["text"],
        "date": "2026-05-24",
        "author": "中年电竞人",
        "source_type": "version_meta",
        "score": 0.81,
    }]


def test_health_reports_new_tk_provider():
    with patch.object(MODULE, "_embedding_readiness", return_value={"ready": True}), \
            TestClient(MODULE.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "mempalace", "wing": "xiaoxue-tk",
                               "embedding": {"ready": True}}


def test_missing_model_refuses_search_and_reindex_without_implicit_download(tmp_path):
    embedding = SimpleNamespace(DOWNLOAD_PATH=tmp_path, EXTRACTED_FOLDER_NAME="onnx")
    with patch.object(MODULE, "get_embedding_function", return_value=embedding), \
            patch.object(MODULE, "search_memories") as search, \
            patch.object(MODULE, "mine") as mine, TestClient(MODULE.app) as client:
        health = client.get("/api/health")
        response = client.post("/api/search", json={"query": "世界赛", "top": 12})
        reindex = client.post("/api/reindex", json={"force": False})

    assert health.status_code == response.status_code == reindex.status_code == 503
    assert health.json()["status"] == "degraded"
    assert response.json()["detail"]["code"] == "embedding_not_ready"
    assert "model.onnx" in response.json()["detail"]["missing_files"]
    search.assert_not_called()
    mine.assert_not_called()


def test_model_readiness_requires_all_nonempty_cached_files(tmp_path):
    folder = tmp_path / "onnx"
    folder.mkdir()
    required = ["config.json", "model.onnx", "special_tokens_map.json",
                "tokenizer_config.json", "tokenizer.json", "vocab.txt"]
    for name in required:
        (folder / name).write_text("cached", encoding="utf-8")
    embedding = SimpleNamespace(DOWNLOAD_PATH=tmp_path, EXTRACTED_FOLDER_NAME="onnx")
    with patch.object(MODULE, "get_embedding_function", return_value=embedding):
        assert MODULE._embedding_readiness()["ready"] is True
        (folder / "model.onnx").write_bytes(b"")
        assert MODULE._embedding_readiness()["missing_files"] == ["model.onnx"]


def test_runtime_paths_can_be_supplied_by_environment():
    with patch.dict(
        MODULE.os.environ,
        {"XIAOXUE_MEMPALACE_SITE_PACKAGES": "~/custom-mempalace/site-packages"},
    ):
        configured = MODULE._mempalace_site_packages()

    assert configured == str(Path.home() / "custom-mempalace/site-packages")


def test_runtime_does_not_probe_unrelated_user_tool_environments():
    with patch.dict(MODULE.os.environ, {}, clear=True):
        configured = MODULE._mempalace_site_packages()

    assert configured == ""
