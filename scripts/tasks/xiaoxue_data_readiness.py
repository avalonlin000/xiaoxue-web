#!/usr/bin/env python3
"""Hermes no-agent wrapper for the canonical Xiaoxue data-readiness pipeline.

Runs data_readiness_pipeline.py and outputs a concise summary instead of
the full JSON manifest.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TARGET = Path("/home/ubuntu/lol_data/scripts/data_readiness_pipeline.py")


def main() -> int:
    if not TARGET.is_file():
        print(f"ERROR: canonical data-readiness pipeline missing: {TARGET}")
        return 2

    cmd = [sys.executable, str(TARGET), *sys.argv[1:]]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(TARGET.parent))

    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        print(f"❌ 数据就绪失败 (exit {result.returncode})")
        if result.stdout.strip():
            print(result.stdout[:2000])
        return result.returncode

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        print(result.stdout[:2000])
        return 0

    ok = data.get("ok") is True
    stages = {
        str(item.get("id")): item
        for item in (data.get("stages") or [])
        if isinstance(item, dict)
    }
    errors = list((data.get("readiness") or {}).get("errors") or [])

    icon = "✅" if ok else "⚠️"
    lines = [f"{icon} 数据就绪 — {'ok' if ok else 'blocked'}"]
    scoregg = stages.get("scoregg_refresh") or {}
    if scoregg:
        lines.append(f"  ScoreGG: {scoregg.get('status', 'unknown')}")
    ts = stages.get("ts_update") or {}
    if ts:
        lines.append(f"  赛程: {ts.get('status', 'unknown')}")
    for error in errors[:5]:
        lines.append(f"  ⚠ {error}")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
