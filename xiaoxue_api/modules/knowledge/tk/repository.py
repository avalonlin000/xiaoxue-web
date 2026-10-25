from __future__ import annotations

import os
from pathlib import Path
import tempfile

import requests


WIKI_DIR = os.environ.get("XIAOXUE_WIKI_DIR", "/home/ubuntu/workspace/knowledge/wiki")
TK_DIR = os.path.join(WIKI_DIR, "小雪电竞", "原始资料", "tk")
MEMPALACE_API = os.environ.get("XIAOXUE_TK_API", "http://localhost:8770/api/search")
MEMPALACE_REINDEX_API = os.environ.get("XIAOXUE_TK_REINDEX_API", "http://localhost:8770/api/reindex")
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
    payload = {"query": query, "top": limit, "source": CURRENT_TK_SOURCE}
    try:
        response = requests.post(MEMPALACE_API, json=payload, timeout=10)
        response.raise_for_status()
        body = response.json()
        results = body.get("results", []) if isinstance(body, dict) else []
        return results if isinstance(results, list) else []
    except (requests.RequestException, ValueError, TypeError):
        return []


def request_reindex() -> bool:
    payload = {"force": False, "source_only": CURRENT_TK_SOURCE}
    try:
        response = requests.post(MEMPALACE_REINDEX_API, json=payload, timeout=3)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False
