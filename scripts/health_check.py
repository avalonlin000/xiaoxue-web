#!/usr/bin/env python3
"""Read-only health check for Xiaoxue project-owned runtime and data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check() -> dict:
    from xiaoxue_api.core import model_runtime

    model = model_runtime.public_identity()
    db = Path(os.environ.get("LOL_DB_PATH", "/home/ubuntu/lol_data/英雄联盟数据库.db"))
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    checks = {
        "project_root": {"ok": (ROOT / "AGENTS.md").is_file(), "path": str(ROOT)},
        "model_config": {"ok": True, **model},
        "main_python": {"ok": Path(sys.executable).is_relative_to(ROOT), "path": sys.executable},
        "tk_python": {"ok": (ROOT / ".venv-tk/bin/python").is_file(), "path": str(ROOT / ".venv-tk/bin/python")},
        "mcp_python": {"ok": (ROOT / ".venv-mcp/bin/python").is_file(), "path": str(ROOT / ".venv-mcp/bin/python")},
        "database": {"ok": True, "path": str(db), "teams": teams},
        "wiki": {"ok": Path("/home/ubuntu/workspace/knowledge/wiki/小雪电竞").is_dir()},
    }
    try:
        with urllib.request.urlopen("http://127.0.0.1:8880/api/health", timeout=8) as response:
            body = json.loads(response.read().decode("utf-8"))
            checks["api"] = {
                "ok": response.status == 200 and body.get("ok") is True,
                "http_status": response.status,
                "status": body.get("status", "unknown"),
                "degraded_modules": [
                    module_id
                    for module_id, module in body.get("modules", {}).items()
                    if module.get("status") in {"degraded", "broken"}
                ],
            }
    except Exception as exc:
        checks["api"] = {"ok": False, "error": type(exc).__name__}
    return {"ok": all(item.get("ok") for item in checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        payload = check()
    except Exception as exc:
        payload = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else
          ("健康检查通过" if payload.get("ok") else "健康检查失败：" + json.dumps(payload, ensure_ascii=False)))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
