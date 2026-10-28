#!/usr/bin/env python3
"""No-agent cron wrapper for 小雪数据库每日刷新.

Runs the deterministic ScoreGG refresh pipeline and prints a compact delivery
summary. Keeping this cron in no-agent mode avoids LLM stream stalls/Broken pipe
from long scheduled conversations.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

ROOT = Path("/home/ubuntu/lol_data")
SCRIPT = ROOT / "scripts" / "scoregg_refresh.py"
LIBS = ROOT / "libs"


def fail(message: str, code: int = 1) -> None:
    print(f"❌ 数据库每日刷新失败：{message}")
    raise SystemExit(code)


def parse_refresh_output(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    patterns = {
        "scan": r"扫描\s+(\d+)\s+天,\s+原始\s+(\d+)\s+条比赛",
        "normalized": r"标准化后:\s+(\d+)\s+条",
        "schedules": r"schedules:\s+(\d+)\s+新增,\s+(\d+)\s+更新",
        "matches": r"matches:\s+(\d+)\s+新增,\s+(\d+)\s+更新",
        "skipped": r"跳过（非LPL/LCK）:\s+(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            fields[key] = "/".join(match.groups())
    return fields


def db_path() -> str:
    sys.path.insert(0, str(LIBS))
    from db_util import get_db_path  # type: ignore

    path = get_db_path()
    if not isinstance(path, str):
        fail(f"db_util.get_db_path() 返回异常类型：{type(path).__name__}")
    return path


def validate_database(path: str) -> dict[str, object]:
    today = date.today()
    future = today + timedelta(days=7)
    conn = sqlite3.connect(path)
    try:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            for table in ["schedules", "matches", "team_3d_data", "teams"]
        }
        latest_update = conn.execute("SELECT MAX(updated_at) FROM schedules").fetchone()[0]
        future_count = conn.execute(
            "SELECT COUNT(*) FROM schedules WHERE date >= ? AND date <= ?",
            (today.isoformat(), future.isoformat()),
        ).fetchone()[0]
        drx_residue = 0
        checks = [
            ("schedules", "team_a"),
            ("schedules", "team_b"),
            ("matches", "team_a_id"),
            ("matches", "team_b_id"),
            ("matches", "winner"),
        ]
        for table, col in checks:
            drx_residue += conn.execute(
                f"SELECT COUNT(*) FROM [{table}] WHERE {col}='DRX'"
            ).fetchone()[0]
        recent_rows = conn.execute(
            """
            SELECT date, COALESCE(time_bjt,''), team_a, team_b, region, stage
            FROM schedules
            WHERE date >= ?
            ORDER BY date, time_bjt
            LIMIT 5
            """,
            (today.isoformat(),),
        ).fetchall()
    finally:
        conn.close()
    return {
        "counts": counts,
        "latest_update": latest_update,
        "future_count": future_count,
        "future_range": f"{today.isoformat()}~{future.isoformat()}",
        "drx_residue": drx_residue,
        "recent_rows": recent_rows,
    }


def refresh_reference_cache() -> int:
    sys.path.insert(0, str(LIBS))
    from db_util import _cache_invalidate, get_cached_teams  # type: ignore

    _cache_invalidate()
    teams = get_cached_teams()
    return len(teams)


def main() -> None:
    if not SCRIPT.exists():
        fail(f"刷新脚本不存在：{SCRIPT}")

    started = datetime.now()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=420,
        env=env,
    )
    output = result.stdout or ""
    if result.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-30:])
        fail(f"scoregg_refresh.py exit={result.returncode}\n{tail}")

    parsed = parse_refresh_output(output)
    path = db_path()
    team_cache_count = refresh_reference_cache()
    validation = validate_database(path)
    counts = cast(dict[str, int], validation["counts"])

    print("✅ 数据库每日刷新完成")
    print(f"时间：{started.strftime('%Y-%m-%d %H:%M:%S')} → {datetime.now().strftime('%H:%M:%S')}")
    if "scan" in parsed:
        days, raw = parsed["scan"].split("/")
        print(f"ScoreGG：扫描 {days} 天，原始 {raw} 条")
    if "normalized" in parsed:
        print(f"标准化：{parsed['normalized']} 条（去重后）")
    if "schedules" in parsed:
        ins, upd = parsed["schedules"].split("/")
        print(f"schedules：{ins} 新增 / {upd} 更新；当前 {counts['schedules']} 行")
    if "matches" in parsed:
        ins, upd = parsed["matches"].split("/")
        print(f"matches：{ins} 新增 / {upd} 更新；当前 {counts['matches']} 行")
    print(f"teams/team_3d：{counts['teams']} 队 / {counts['team_3d_data']} 条三维数据")
    print(f"未来7天赛程：{validation['future_count']} 场（{validation['future_range']}）")
    print(f"schedules 最新 updated_at：{validation['latest_update']}")
    print(f"缓存：已 _cache_invalidate()，重新加载 {team_cache_count} 队")
    print(f"DRX 残留：{validation['drx_residue']}")
    rows = cast(list[tuple[Any, ...]], validation["recent_rows"])
    if rows:
        print("最近赛程预览：")
        for row in rows:
            d, t, a, b, region, stage = row
            time_part = (t or "").split(" ")[-1] if t else ""
            print(f"- {d} {time_part} {a} vs {b} [{region}] {stage}")


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_database_daily_refresh.py（无参数；刷新数据库）")
        raise SystemExit(0)
    main()
