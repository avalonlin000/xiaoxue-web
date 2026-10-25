#!/usr/bin/env python3
"""从 lolesports 官方接口同步队伍名单（首发表）。

默认只做 dry-run，打印每个队的变化；加 --apply 才写库。
写库方式：旧记录置为 inactive（保留历史），新记录以 source_kind=lolesports 写入。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "xiaoxue_api/modules/match/event/config.json"
DB = Path("/home/ubuntu/lol_data/英雄联盟数据库.db")
API = "https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US"
KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
POS = {"top": ("上单", "TOP"), "jungle": ("打野", "JUNGLE"), "mid": ("中单", "MID"),
       "bottom": ("ADC", "BOT"), "support": ("辅助", "SUPPORT")}
SKIP = re.compile(r"academy|challengers|rookies|youth", re.I)


def fetch_teams() -> list[dict]:
    req = urllib.request.Request(API, headers={"x-api-key": KEY, "User-Agent": "xiaoxue/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["data"]["teams"]


def choose_main(candidates: list[dict], db_name: str) -> dict | None:
    rows = [t for t in candidates if not SKIP.search(t.get("name") or "")]
    if not rows:
        return None
    exact = [t for t in rows if (t.get("name") or "").casefold() == (db_name or "").casefold()]
    if exact:
        return exact[0]
    return max(rows, key=lambda t: len(t.get("players") or []))


def players_of(team: dict) -> list[dict]:
    out, seen_pos = [], set()
    for p in team.get("players") or []:
        role = (p.get("role") or "").lower()
        cn, pos = POS.get(role, (role or "选手", (role or "").upper()))
        starter = 1 if pos and pos not in seen_pos else 0
        seen_pos.add(pos)
        out.append({"name": (p.get("summonerName") or "").strip(), "role": cn, "position": pos, "starter": starter})
    return [p for p in out if p["name"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    s16 = cfg.get("confirmed_teams") or []
    teams_api = fetch_teams()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat(timespec="seconds")

    changed = 0
    for code in s16:
        row = conn.execute("select team_id, name from teams where short_name=?", (code,)).fetchone()
        if not row:
            print(f"{code:5} 数据库没有这支队伍，跳过")
            continue
        cands = [t for t in teams_api if (t.get("code") or "").upper() == code.upper()]
        main_team = choose_main(cands, row["name"])
        if not main_team:
            print(f"{code:5} 官方接口没有可用名单")
            continue
        new = players_of(main_team)
        old = [dict(r) for r in conn.execute(
            "select player_name, role, position, is_starter from rosters where team_id=? and status='active'", (row["team_id"],))]
        old_names = {r["player_name"] for r in old}
        new_names = {p["name"] for p in new}
        old_ci = {n.casefold() for n in old_names}
        new_ci = {n.casefold() for n in new_names}
        added = sorted(n for n in new_names if n.casefold() not in old_ci)
        removed = sorted(n for n in old_names if n.casefold() not in new_ci)
        if added or removed:
            changed += 1
            print(f"{code:5} {row['team_id']:12} 旧 {len(old):2} 人 → 新 {len(new):2} 人 | 新增 {added} | 移除 {removed}")
        if args.apply:
            conn.execute("update rosters set status='inactive', updated_at=? where team_id=? and status='active'", (now, row["team_id"]))
            for p in new:
                conn.execute(
                    """insert into rosters (roster_id, team_id, player_id, player_name, role, position, is_starter,
                       join_date, created_at, leave_date, status, transfer_notes, source_kind, source_ref,
                       source_updated_at, verified_at, updated_at)
                       values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"roster-{row['team_id']}-{p['name'].lower().replace(' ', '-')}", row["team_id"], None, p["name"],
                     p["role"], p["position"], p["starter"], None, now, None, "active", None,
                     "lolesports", API, now, now, now),
                )
    if args.apply:
        conn.commit()
        print("已写入，共更新", changed, "支队伍")
    else:
        print("dry-run：共", changed, "支队伍有变化；加 --apply 才写库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
