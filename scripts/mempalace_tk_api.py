"""Small HTTP adapter exposing the Xiaoxue TK wing in MemPalace.

The Xiaoxue web app and report scripts are long-lived HTTP/CLI consumers, while
MemPalace's supported runtime interface is MCP.  This adapter keeps that
boundary local and narrow: only the TK wing is searchable, and reindexing is
delegated to MemPalace's own incremental miner.
"""

from __future__ import annotations

import re
import os
import sys
import threading
import logging
from pathlib import Path


def _mempalace_site_packages() -> str:
    configured = os.getenv("XIAOXUE_MEMPALACE_SITE_PACKAGES", "").strip()
    if configured:
        return str(Path(configured).expanduser())
    candidates = sorted(
        (Path.home() / ".local/share/uv/tools/mempalace/lib").glob("python*/site-packages"),
        reverse=True,
    )
    return str(candidates[0]) if candidates else ""


MEMPALACE_SITE_PACKAGES = _mempalace_site_packages()
if MEMPALACE_SITE_PACKAGES and MEMPALACE_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, MEMPALACE_SITE_PACKAGES)

from fastapi import FastAPI
from pydantic import BaseModel, Field

from mempalace.miner import mine
from mempalace.searcher import search_memories


PALACE = str(
    Path(os.getenv("XIAOXUE_MEMPALACE_PALACE", "~/.mempalace/palace")).expanduser()
)
TK_SOURCE_DIR = str(
    Path(os.getenv("XIAOXUE_TK_SOURCE_DIR", "~/.local/share/xiaoxue/tk")).expanduser()
)
TK_WING = os.getenv("XIAOXUE_MEMPALACE_WING", "xiaoxue-tk")
_DATE_RE = re.compile(r"(?:created|date|period_start)\s*:\s*(\d{4}-\d{2}-\d{2})")
_SOURCE_TYPE_RE = re.compile(r"^source_type:\s*(.+)$", re.MULTILINE)
_SOURCE_RE = re.compile(r"^source:\s*(.+)$", re.MULTILINE)
_reindex_lock = threading.Lock()
_reindex_running = False
_reindex_error: str | None = None
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Xiaoxue TK MemPalace adapter", version="1.0")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top: int = Field(default=10, ge=1, le=60)
    source: str | None = None


class ReindexRequest(BaseModel):
    force: bool = False
    source_only: str | None = None


def _date_from(text: str, metadata: dict) -> str:
    match = _DATE_RE.search(text[:1200])
    if match:
        return match.group(1)
    created_at = str(metadata.get("created_at") or "")
    return created_at[:10] if len(created_at) >= 10 else ""


def _map_result(item: dict) -> dict:
    metadata = item.get("metadata") or item
    text = str(item.get("text") or "")
    source_file = str(item.get("source_file") or metadata.get("source_file") or "")
    source_type = str(metadata.get("source_type") or "")
    if not source_type:
        match = _SOURCE_TYPE_RE.search(text[:1200])
        source_type = match.group(1).strip() if match else "mempalace"
    source = str(metadata.get("source") or "")
    if not source:
        match = _SOURCE_RE.search(text[:1200])
        source = match.group(1).strip() if match else ""
    return {
        "id": source_file,
        "title": source_file,
        "text": text,
        "date": _date_from(text, metadata),
        "author": source,
        "source_type": source_type,
        "score": float(item.get("similarity") or 0.0),
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "provider": "mempalace", "wing": TK_WING}


@app.get("/api/stats")
def stats() -> dict:
    return {
        "status": "ok" if _reindex_error is None else "degraded",
        "provider": "mempalace",
        "wing": TK_WING,
        "source": TK_SOURCE_DIR,
        "reindex_running": _reindex_running,
        "last_reindex_error": _reindex_error,
    }


@app.post("/api/search")
def search(payload: SearchRequest) -> dict:
    result = search_memories(
        payload.query,
        PALACE,
        wing=TK_WING,
        n_results=payload.top,
        candidate_strategy="union",
    )
    if result.get("error"):
        return {"error": result["error"], "results": []}
    return {"results": [_map_result(item) for item in result.get("results", [])]}


def _run_reindex() -> None:
    global _reindex_error, _reindex_running
    try:
        mine(TK_SOURCE_DIR, PALACE, wing_override=TK_WING, agent="xiaoxue-tk-api")
        _reindex_error = None
    except Exception as exc:
        _reindex_error = str(exc)
        LOGGER.exception("MemPalace TK reindex failed")
    finally:
        with _reindex_lock:
            _reindex_running = False


@app.post("/api/reindex")
def reindex(payload: ReindexRequest) -> dict:
    del payload
    global _reindex_error, _reindex_running
    with _reindex_lock:
        if _reindex_running:
            return {"status": "running", "provider": "mempalace", "wing": TK_WING}
        _reindex_running = True
        _reindex_error = None
    threading.Thread(target=_run_reindex, name="mempalace-tk-reindex", daemon=True).start()
    return {"status": "started", "provider": "mempalace", "wing": TK_WING}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8770)
