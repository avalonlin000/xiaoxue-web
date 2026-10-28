from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("project_health_check", ROOT / "scripts/health_check.py")
health_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(health_check)


class _Response:
    status = 200

    def __init__(self, body: dict):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")


def test_api_degraded_body_is_not_healthy():
    response = _Response(
        {
            "ok": False,
            "status": "degraded",
            "modules": {
                "daily_content": {"status": "broken"},
                "team": {"status": "healthy"},
            },
        }
    )

    with mock.patch.object(health_check.urllib.request, "urlopen", return_value=response):
        result = health_check.check()

    assert result["checks"]["api"] == {
        "ok": False,
        "http_status": 200,
        "status": "degraded",
        "degraded_modules": ["daily_content"],
    }
    assert result["ok"] is False
