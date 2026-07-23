from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

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
    with patch.object(MODULE, "search_memories", return_value={"results": [raw]}):
        with TestClient(MODULE.app) as client:
            response = client.post("/api/search", json={"query": "BLG 纪律性", "top": 3})

    assert response.status_code == 200
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
    with TestClient(MODULE.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "mempalace", "wing": "xiaoxue-tk"}


def test_runtime_paths_can_be_supplied_by_environment():
    with patch.dict(
        MODULE.os.environ,
        {"XIAOXUE_MEMPALACE_SITE_PACKAGES": "~/custom-mempalace/site-packages"},
    ):
        configured = MODULE._mempalace_site_packages()

    assert configured == str(Path.home() / "custom-mempalace/site-packages")
