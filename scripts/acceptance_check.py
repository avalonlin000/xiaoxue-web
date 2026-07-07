#!/usr/bin/env python3
"""Xiaoxue workbench smoke acceptance checks."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8880"


def request(path: str, *, method: str = "GET", body: dict | None = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_health() -> None:
    data = request("/api/health")
    assert_true(data.get("ok") is True, f"health not ok: {data}")
    checks = data.get("checks", {})
    for key in ("database", "dist", "tk_dir", "skill_dirs", "memory_bank", "market_notes", "disk"):
        assert_true(key in checks, f"missing health check: {key}")
        assert_true(checks[key].get("ok") is True, f"{key} check failed: {checks[key]}")
    print("health ok")


def check_market_notes() -> None:
    marker = f"acceptance-{int(time.time())}"
    created = request(
        "/api/market-notes",
        method="POST",
        body={
            "game": "lol",
            "match_name": marker,
            "direction": "",
            "total_lean": "放弃",
            "score_note": "",
            "reason": "验收脚本：只验证手写草稿保存/读取/删除，不生成方向。",
            "confidence": "中",
            "review": "acceptance cleanup",
            "linked_team": "EDG",
        },
    )
    record = created.get("record") or {}
    note_id = record.get("id")
    assert_true(created.get("ok") is True and note_id, f"market note create failed: {created}")

    listed = request("/api/market-notes?game=lol&limit=80")
    records = listed.get("records", [])
    assert_true(any(r.get("id") == note_id and r.get("match_name") == marker for r in records), "created note not listed")

    deleted = request(f"/api/market-notes/{note_id}", method="DELETE")
    assert_true(deleted.get("ok") is True, f"market note delete failed: {deleted}")

    listed_after = request("/api/market-notes?game=lol&limit=80")
    assert_true(all(r.get("id") != note_id for r in listed_after.get("records", [])), "deleted note still listed")
    print("market-notes ok")


def check_profile_fallback(team: str = "EDG") -> None:
    data = request(f"/api/profile-full/{team}")
    assert_true(data.get("found") is True, f"profile not found for {team}: {data}")
    source = data.get("source")
    assert_true(source in {"wiki", "skill", "database_fallback"}, f"unexpected profile source: {source}")
    if source == "database_fallback":
        html = data.get("html", "")
        assert_true("数据库只读画像" in html and "不替代人工画像" in html, "fallback profile boundary missing")
    print(f"profile ok ({team}, source={source})")


def check_version_understanding(team: str = "EDG") -> None:
    data = request(f"/api/version-understanding/{team}")
    assert_true(data.get("ok") is True, f"version understanding not ok: {data}")
    assert_true(data.get("team") == team, f"unexpected version team: {data}")
    assert_true(data.get("boundary") == "只读聚合现有资料，不自动生成版本判断", "version boundary missing")
    assert_true(isinstance(data.get("tk_items"), list), "version tk_items is not a list")
    print(f"version-understanding ok ({team})")


def main() -> int:
    try:
        check_health()
        check_market_notes()
        check_profile_fallback()
        check_version_understanding()
    except Exception as exc:
        print(f"acceptance failed: {exc}", file=sys.stderr)
        return 1
    print("acceptance ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
