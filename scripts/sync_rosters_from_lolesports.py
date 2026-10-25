#!/usr/bin/env python3
"""从 lolesports 官方接口同步队伍名单，并尽量保留已知首发。

- 已有首发的队伍：名单里仍在的旧首发继续算首发；空出的位置用新名单按位置补一个。
- 没有首发的队伍：按位置各取第一个作为首发。
- 默认 dry-run；--apply 才写库。旧记录置 inactive 保留历史，新记录带 lolesports 来源。
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
    return exact[0] if exact else max(rows, key=lambda t: len(t.get("players") or []))


def roster_players(team: dict) -> list[dict]:
    out = []
    for p in team.get("players") or []:
        name = (p.get("summonerName") or "").strip()
        if not name:
            continue
        role = (p.get("role") or "").lower()
        cn, pos = POS.get(role, (role or "选手", (role or "").upper()))
        out.append({"name": name, "role": cn, "position": pos})
    return out


def mark_starters(players: list[dict], old_starters: list[dict]) -> list[dict]:
    by_ci = {p["name"].casefold(): p for p in players}
    covered: set[str] = set()
    for old in old_starters:
        hit = by_ci.get(str(old["player_name"]).casefold())
        if hit and hit["position"] not in covered:
            hit["starter"] = 1
            covered.add(hit["position"])
    valid = {value[1] for value in POS.values()}
    for p in players:
        if p.get("starter"):
            continue
        if len(covered) < 5 and p["position"] in valid and p["position"] not in covered:
            p["starter"] = 1
            covered.add(p["position"])
        else:
            p["starter"] = 0
    return players


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    s16 = cfg.get("confirmed_teams") or []
    api_teams = fetch_teams()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat(timespec="seconds")
    changed = 0

    for code in s16:
        row = conn.execute("select team_id, name from teams where short_name=?", (code,)).fetchone()
        if not row:
            print(f"{code:5} 数据库没有这支队伍，跳过")
            continue
        cands = [t for t in api_teams if (t.get("code") or "").upper() == code.upper()]
        main_team = choose_main(cands, row["name"])
        if not main_team:
            print(f"{code:5} 官方接口没有可用名单")
            continue
        players = roster_players(main_team)
        old = [dict(r) for r in conn.execute(
            "select player_name, position, is_starter from rosters where team_id=? and status='active' and coalesce(leave_date,'')=''",
            (row["team_id"],))]
        old_starters = [r for r in old if int(r["is_starter"] or 0) == 1]
        players = mark_starters(players, old_starters)
        starters = [p["name"] for p in players if p.get("starter")]
        old_names = {r["player_name"] for r in old}
        new_names = {p["name"] for p in players}
        old_ci = {n.casefold() for n in old_names}
        new_ci = {n.casefold() for n in new_names}
        added = sorted(n for n in new_names if n.casefold() not in old_ci)
        removed = sorted(n for n in old_names if n.casefold() not in new_ci)
        if added or removed or len(old_starters) != len(starters):
            changed += 1
            print(f"{code:5} {row['team_id']:14} {len(old):2}→{len(players):2} 人 | 首发 {starters} | 新增 {added} | 移除 {removed}")
        if args.apply:
            conn.execute("update rosters set status='inactive', updated_at=? where team_id=? and status='active'", (now, row["team_id"]))
            for p in players:
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
