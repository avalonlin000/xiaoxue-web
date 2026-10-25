#!/usr/bin/env python3
"""Refresh the locally served LoL champion snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xiaoxue_api.modules.methods.hero_static.service import refresh_champion_cache


def main() -> int:
    parser = argparse.ArgumentParser(description='刷新本地英雄静态资料')
    parser.add_argument('--version', default='', help='指定 Data Dragon 版本；默认最新正式版本')
    args = parser.parse_args()
    print(json.dumps(refresh_champion_cache(args.version), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
