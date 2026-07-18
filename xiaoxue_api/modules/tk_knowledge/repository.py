from __future__ import annotations

import os
from pathlib import Path
import tempfile

import requests


WIKI_DIR = os.environ.get("XIAOXUE_WIKI_DIR", "/home/ubuntu/workspace/knowledge/wiki")
TK_DIR = os.path.join(WIKI_DIR, "小雪电竞", "原始资料", "tk")
RAG_API = os.environ.get("XIAOXUE_RAG_API", "http://localhost:8768/api/search")
REINDEX_API = os.environ.get("XIAOXUE_REINDEX_API", "http://localhost:8768/api/reindex")
CURRENT_TK_SOURCE = "wiki/小雪电竞/原始资料/tk"


def list_documents() -> list[dict]:
    if not os.path.isdir(TK_DIR):
        return []
    documents = []
    for filename in os.listdir(TK_DIR):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(TK_DIR, filename)
        try:
            stat = os.stat(path)
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        documents.append({
            "filename": filename,
            "path": path,
            "content": content,
            "mtime": stat.st_mtime,
        })
    return documents


def read_document(filename: str) -> dict | None:
    path = os.path.join(TK_DIR, filename)
    try:
        stat = os.stat(path)
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return {"filename": filename, "path": path, "content": content, "mtime": stat.st_mtime}


def write_document(filename: str, content: str) -> str:
    os.makedirs(TK_DIR, exist_ok=True)
    target = os.path.join(TK_DIR, filename)
    fd, temporary = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=TK_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return target


def delete_document(filename: str) -> bool:
    path = os.path.join(TK_DIR, filename)
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    return True


def search_rag(query: str, limit: int) -> list[dict]:
    try:
        response = requests.post(
            RAG_API,
            json={"query": query, "top": limit, "source": CURRENT_TK_SOURCE},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return results if isinstance(results, list) else []
    except (requests.RequestException, ValueError, TypeError):
        return []


def request_reindex() -> bool:
    try:
        response = requests.post(
            REINDEX_API,
            json={"force": False, "source_only": CURRENT_TK_SOURCE},
            timeout=3,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False
