#!/usr/bin/env python3
"""小雪日报随机抽查 cron 入口（no-agent 版）。

stdout 由 Hermes cron 直接投递；全绿输出 [SILENT] 不发群消息，
有异常输出结构化告警并退出码 1。
"""
from __future__ import annotations

import os
import sys

TARGET = "/home/ubuntu/lol_data/scripts/spotcheck_daily.py"

if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_daily_spotcheck.py（无参数；抽查日报）")
        raise SystemExit(0)
    if not os.path.isfile(TARGET):
        print(f"ERROR: spotcheck script missing: {TARGET}")
        raise SystemExit(2)
    os.execv(sys.executable, [sys.executable, TARGET])
