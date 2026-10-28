#!/usr/bin/env python3
"""Compatibility wrapper for knowledge-import log upload.

Canonical implementation lives at:
/home/ubuntu/lol_data/scripts/upload_import_log.py

Hermes cron job d3059eeed1fa may resolve script names from ~/.hermes/scripts,
so keep this wrapper to avoid executing the obsolete markdown +create flow.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

TARGET = Path("/home/ubuntu/lol_data/scripts/upload_import_log.py")

if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：upload_import_log.py（无参数；上传最新导入日志，内置去重）")
        sys.exit(0)
    if not TARGET.exists():
        print(f"ERROR: canonical upload script missing: {TARGET}")
        sys.exit(2)
    runpy.run_path(str(TARGET), run_name="__main__")
