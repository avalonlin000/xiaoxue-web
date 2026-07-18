from __future__ import annotations

import json
import os
from pathlib import Path


STATE_PATH = Path(
    os.environ.get("WEREAD_BRIDGE_STATE", "/tmp/weread_login_bridge.json")
)
SECRET_PATH = Path(
    os.environ.get(
        "WEREAD_BRIDGE_SECRET",
        "/home/ubuntu/.hermes/state/weread_login_bridge_secret",
    )
)


def read_secret() -> str:
    try:
        return SECRET_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def read_state() -> dict | None:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
