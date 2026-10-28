#!/usr/bin/env python3
"""No-agent entry for the only Xiaoxue LOL daily-report production path.

Runs daily_pipeline.py and outputs a concise one-line summary instead of
the full JSON manifest, so the cron delivery stays readable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

TARGET = Path("/home/ubuntu/lol_data/scripts/daily_pipeline.py")


def pipeline_environment() -> dict[str, str]:
    """Enable only the read-only frozen consumer, using the configured workbench.

    An explicitly present environment override (including empty/off) is kept.
    Neither collection nor refresh is called by the daily producer.
    """
    environment = dict(os.environ)
    if "XIAOXUE_MATERIALS_API_BASE" not in environment:
        try:
            sys.path.insert(0, str(TARGET.parent.parent / "libs"))
            from config import get_service_url
            environment["XIAOXUE_MATERIALS_API_BASE"] = get_service_url("workbench_api_url")
        except (OSError, ValueError, KeyError, ImportError):
            print("WARNING: 工作台成果地址暂不可读，已有日报流程保留。", file=sys.stderr)
    return environment


def main() -> int:
    if not TARGET.is_file():
        print(f"ERROR: canonical daily pipeline missing: {TARGET}")
        return 2

    cmd = [sys.executable, str(TARGET), "--date", date.today().isoformat(), "--publish"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(TARGET.parent), env=pipeline_environment())

    # Always print stderr (pipeline diagnostics)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        # On failure, show full output for debugging
        print(f"❌ 日报失败 (exit {result.returncode})")
        if result.stdout.strip():
            print(result.stdout[:2000])
        return result.returncode

    # On success, parse JSON and print concise summary
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        # Fallback: just print raw output if not valid JSON
        print(result.stdout[:2000])
        return 0

    d = data.get("date", date.today().isoformat())
    audit_ok = data.get("audit_ok", False)
    published = data.get("published", False)
    parts = data.get("destinations", {}).get("feishu", {}).get("parts", [])

    status = "✅" if audit_ok and published else "⚠️"
    part_count = len(parts)
    titles = [p.get("title", "") for p in parts if p.get("title")]

    lines = [f"{status} 日报 {d} — {part_count} 篇"]
    for t in titles:
        lines.append(f"  • {t}")

    # Add main index URL if available
    main_url = data.get("destinations", {}).get("feishu", {}).get("url")
    if main_url:
        lines.append(f"  {main_url}")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_daily_report.py（无参数；执行日报生产与发布）")
        raise SystemExit(0)
    raise SystemExit(main())
