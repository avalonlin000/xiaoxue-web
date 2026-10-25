#!/usr/bin/env python3
"""Read-only, module-by-module Xiaoxue workbench acceptance checks."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/xiaoxue-web")
from xiaoxue_api.modules.team.ts.repository import active_stage as _active_stage  # noqa: E402


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


def check_project_modules() -> None:
    data = request("/api/modules")
    modules = data.get("modules") or []
    assert_true(data.get("schema") == "xiaoxue-module-contract-v1", "project module contract schema missing")
    assert_true(len(modules) == 8, f"unexpected project module count: {len(modules)}")
    assert_true(all(item.get("read_capability") for item in modules), "module read contract missing")
    assert_true(all(item.get("readback_capability") for item in modules), "module readback contract missing")
    print(f"project-modules ok ({len(modules)} registered)")


def check_ts_display(team: str = "BLG") -> None:
    data = request(f"/api/fundamentals/teams?scope=lpl&team={team}&limit=1")
    rows = data.get("teams") or []
    assert_true(len(rows) == 1 and rows[0].get("short_name") == team, f"TS team not found: {data}")
    display = rows[0].get("ts_display") or {}
    fields = ("power_score", "volatility_score", "trend", "momentum", "status")
    assert_true(all(field in display for field in fields), f"TS display fields missing: {display}")
    assert_true(rows[0].get("ts_stage") == _active_stage(), f"TS is not current stage: {rows[0]}")
    print(f"ts-display ok ({team}: {display})")


def check_tk_read(team: str = "BLG") -> None:
    data = request(f"/api/tk/search?q={team}&limit=1")
    assert_true(isinstance(data.get("results"), list), "TK result list missing")
    print(f"tk-read ok ({team}: {len(data.get('results', []))} result(s))")


def check_health() -> None:
    data = request("/api/health")
    modules = data.get("modules") or {}
    assert_true(bool(modules), "health response has no module states")
    broken = [item for item in modules.values() if item.get("status") == "broken"]
    disabled = [item for item in modules.values() if item.get("status") == "disabled"]
    critical = [item for item in broken if item.get("critical")]
    for item in broken:
        print(f"  待修: {item.get('name')} — {item.get('message')}")
    for item in disabled:
        print(f"  暂停: {item.get('name')} — {item.get('message')}")
    assert_true(not critical, f"critical modules unavailable: {critical}")
    print(f"module-health {data.get('status')} ({len(modules) - len(broken) - len(disabled)} healthy)")


def check_profile_fallback(team: str = "EDG") -> None:
    data = request(f"/api/profile-full/{team}")
    assert_true(data.get("found") is True, f"profile not found for {team}: {data}")
    source = data.get("source")
    assert_true(source in {"team_profile", "wiki", "skill", "database_fallback"}, f"unexpected profile source: {source}")
    if source == "database_fallback":
        html = data.get("html", "")
        assert_true("资料总览" in html and "队伍 TK 共" in html, "fallback profile boundary missing")
    print(f"profile ok ({team}, source={source})")


def check_version_understanding(team: str = "EDG") -> None:
    data = request(f"/api/version-understanding/{team}")
    assert_true(data.get("ok") is True, f"version understanding not ok: {data}")
    assert_true(data.get("team") == team, f"unexpected version team: {data}")
    assert_true(data.get("boundary") == "只读聚合现有资料，不自动生成版本判断", "version boundary missing")
    assert_true(isinstance(data.get("tk_items"), list), "version tk_items is not a list")
    print(f"version-understanding ok ({team})")


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base.rstrip("/")

    checks = [
        ("项目模块合同", check_project_modules),
        ("模块状态", check_health),
        ("TS 展示", check_ts_display),
        ("队伍画像", lambda: check_profile_fallback("BLG")),
        ("TK 读取", check_tk_read),
        ("版本理解", check_version_understanding),
    ]
    failures = []
    for name, check in checks:
        try:
            check()
        except Exception as exc:
            failures.append((name, str(exc)))
            print(f"{name} failed: {exc}", file=sys.stderr)

    if failures:
        print(f"acceptance completed: {len(failures)} module(s) failed", file=sys.stderr)
        return 1
    print("acceptance ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
