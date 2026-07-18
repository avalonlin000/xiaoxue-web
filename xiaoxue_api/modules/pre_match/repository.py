from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")


def market_labels() -> dict[str, str]:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return ((payload.get("pre_match") or {}).get("market_labels") or {})
