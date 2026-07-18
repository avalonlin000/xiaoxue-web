from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_event_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_plan(path: str) -> dict | None:
    target = Path(path)
    if not target.is_file():
        return None
    return {
        "content": target.read_text(encoding="utf-8"),
        "updated_at": datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }
