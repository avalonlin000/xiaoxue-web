from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
