from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_artifact(path: str, max_bytes: int = 12000) -> dict:
    exists = os.path.exists(path)
    if not exists:
        return {"exists": False, "updated_at": None, "size_bytes": 0, "content": ""}
    stat = os.stat(path)
    with open(path, encoding="utf-8") as artifact:
        content = artifact.read(max_bytes)
    return {
        "exists": True,
        "updated_at": stat.st_mtime,
        "size_bytes": stat.st_size,
        "content": content,
    }
