#!/usr/bin/env python3
"""统计小雪真实会话里的工具使用结构，用来验收「MCP 替代手拼 sqlite3/curl」。

用法：
    python3 scripts/hermes/mcp_usage_metrics.py --days 30
    python3 scripts/hermes/mcp_usage_metrics.py --days 7 --json

口径：
- 数据来自 Hermes state.db 的 messages（assistant.tool_calls + tool 结果）。
- 「DB 手拼」= terminal 命令里出现 sqlite3 / PRAGMA / sqlite_master。
- 「API 手拼」= terminal 命令里 curl 本地 8xxx 端口或带 /api/ 路径。
- 只统计工具调用，不评估回答质量。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

DEFAULT_DB = Path("/home/ubuntu/.hermes/state.db")
MCP_PREFIX = "mcp__xiaoxue_product__xiaoxue_"

DB_MANUAL = re.compile(r"sqlite3|PRAGMA|sqlite_master")
API_MANUAL = re.compile(r"curl[^\n]*(127\.0\.0\.1:8|localhost:8)|/api/")
ENGINEERING = re.compile(r"\bgit |\bnpm |pytest|systemctl|journalctl|\bpip |py_compile|\bss -|\bps aux|\bkill ")


def classify_terminal(command: str) -> str:
    if DB_MANUAL.search(command):
        return "db_manual"
    if API_MANUAL.search(command):
        return "api_manual"
    if ENGINEERING.search(command):
        return "engineering"
    return "other"


def collect(db_path: Path, days: int) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    since = f"-{int(days)} day"

    tool_calls: Counter[str] = Counter()
    terminal_kinds: Counter[str] = Counter()
    result_chars: dict[str, list[int]] = {}

    rows = conn.execute(
        "SELECT tool_name, tool_calls, content, role, timestamp FROM messages "
        "WHERE timestamp > strftime('%s','now',?)",
        (since,),
    )
    for row in rows:
        if row["role"] == "assistant" and row["tool_calls"]:
            try:
                calls = json.loads(row["tool_calls"])
            except (TypeError, ValueError):
                calls = []
            for call in calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                if not name:
                    continue
                tool_calls[name] += 1
                if name == "terminal":
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except (TypeError, ValueError):
                        arguments = {}
                    terminal_kinds[classify_terminal(str(arguments.get("command") or ""))] += 1
        elif row["role"] == "tool" and row["tool_name"]:
            result_chars.setdefault(row["tool_name"], []).append(len(row["content"] or ""))
    conn.close()

    total = sum(tool_calls.values()) or 1
    mcp_calls = sum(count for name, count in tool_calls.items() if name.startswith(MCP_PREFIX))
    terminal_total = tool_calls.get("terminal", 0) or 1
    averages = {
        name: round(sum(lengths) / len(lengths))
        for name, lengths in result_chars.items()
        if lengths
    }
    return {
        "days": days,
        "tool_calls_total": total,
        "mcp_calls": mcp_calls,
        "mcp_share_pct": round(100 * mcp_calls / total, 1),
        "terminal_calls": tool_calls.get("terminal", 0),
        "terminal_breakdown": dict(terminal_kinds),
        "db_manual_pct_of_terminal": round(100 * terminal_kinds.get("db_manual", 0) / terminal_total, 1),
        "top_mcp_tools": [
            [name.replace(MCP_PREFIX, ""), count]
            for name, count in tool_calls.most_common()
            if name.startswith(MCP_PREFIX)
        ][:12],
        "avg_result_chars": dict(sorted(averages.items(), key=lambda kv: -kv[1])[:10]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    metrics = collect(args.db, args.days)
    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return

    print(f"窗口：最近 {metrics['days']} 天")
    print(f"工具调用总数：{metrics['tool_calls_total']}")
    print(f"MCP 调用：{metrics['mcp_calls']}（占 {metrics['mcp_share_pct']}%）")
    print(f"终端调用：{metrics['terminal_calls']}")
    for kind, label in (("db_manual", "数据库手拼"), ("api_manual", "接口手拼"),
                        ("engineering", "工程运维"), ("other", "其他")):
        count = metrics["terminal_breakdown"].get(kind, 0)
        print(f"  {label}：{count}")
    print(f"数据库手拼占终端调用：{metrics['db_manual_pct_of_terminal']}%")
    print("MCP 工具使用排行：")
    for name, count in metrics["top_mcp_tools"]:
        print(f"  {count:4d}  {name}")
    print("平均返回字符（最重的几项）：")
    for name, chars in metrics["avg_result_chars"].items():
        print(f"  {chars:6d}  {name.replace(MCP_PREFIX, '')}")


if __name__ == "__main__":
    main()
