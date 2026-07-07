"""Build Xiaoxue pre-match trading judgment report.

This script writes the first-stage trading layer for the existing daily report.
It reuses the xiaoxue-web backend helpers so the API preview and file output
share the same team trading-note rules.
"""
from __future__ import annotations

import argparse
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main  # noqa: E402


def build_report(date_value: str, limit: int) -> tuple[str, str]:
    date_str = main._resolve_daily_content_date(date_value)
    matches = main._load_schedule_matches(date_str, limit=limit)
    markdown = main._render_pre_match_trading_report(date_str, matches)
    return date_str, markdown


def main_cli() -> int:
    parser = argparse.ArgumentParser(description="Build pre-match trading judgment report.")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=12, help="Max schedule matches")
    parser.add_argument("--output", default="", help="Output markdown path")
    parser.add_argument("--print-only", action="store_true", help="Print markdown instead of writing")
    args = parser.parse_args()

    date_str, markdown = build_report(args.date, args.limit)
    if args.print_only:
        print(markdown)
        return 0

    output = args.output or os.path.join(main.DAILY_CONTENT_ROOT, f"赛前交易判断日报_{date_str}.md")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
