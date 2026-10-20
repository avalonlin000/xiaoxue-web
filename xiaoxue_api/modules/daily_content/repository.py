from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_artifact(path: str, max_bytes: int = 12000) -> dict:
    exists = os.path.exists(path)
    if not exists:
        return {"exists": False, "updated_at": None, "size_bytes": 0, "content": "", "sha256": ""}
    stat = os.stat(path)
    with open(path, encoding="utf-8") as artifact:
        content = artifact.read(max_bytes)
    digest = hashlib.sha256()
    with open(path, "rb") as artifact:
        for chunk in iter(lambda: artifact.read(65536), b""):
            digest.update(chunk)
    return {
        "exists": True,
        "updated_at": stat.st_mtime,
        "size_bytes": stat.st_size,
        "content": content,
        "sha256": digest.hexdigest(),
    }


def read_publication_manifest(report_path: str, date_str: str) -> dict:
    """Read the canonical receipt beside a whitelisted report, without writing."""
    path = Path(report_path).with_name(f"daily_run_manifest_{date_str}.json")
    try:
        with path.open(encoding="utf-8") as source:
            text = source.read(2_000_001)
        if len(text) > 2_000_000:
            return {"status": "invalid", "manifest": {}}
        payload = json.loads(text)
    except FileNotFoundError:
        return {"status": "missing", "manifest": {}}
    except (OSError, UnicodeError, ValueError):
        return {"status": "invalid", "manifest": {}}
    if not isinstance(payload, dict):
        return {"status": "invalid", "manifest": {}}
    return {"status": "ok", "manifest": payload}
