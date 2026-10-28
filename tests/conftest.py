"""Keep every test process away from live collection state by default."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_collection_root(tmp_path, monkeypatch):
    """Application startup and worker subprocesses must use test-only state.

    A few API tests exercise the real FastAPI lifespan, which resumes stored
    collection tasks. Without a process-wide default, tests that do not touch
    collection directly could dispatch the production queue.
    """
    monkeypatch.setenv("XIAOXUE_COLLECTION_DIR", str(tmp_path / "collection-tests"))
