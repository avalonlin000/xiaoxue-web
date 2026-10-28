#!/usr/bin/env python3
"""按需把「小雪产品能力」临时接给其它 Hermes profile（默认关闭）。

钧钧 2026-10-27 的口径：小雪产品 MCP 主要给小雪用，小白和结衣不默认接，
真需要时再开，用完关掉；写入能力始终只留在小雪。

用法：
    python3 scripts/hermes/xiaoxue_mcp_toggle.py --profile xiaobai --status
    python3 scripts/hermes/xiaoxue_mcp_toggle.py --profile xiaobai --on --read-only
    python3 scripts/hermes/xiaoxue_mcp_toggle.py --profile xiaobai --off
    （加 --dry-run 只看将要改什么）

改动范围只有目标 profile 的 config.yaml：
- mcp_servers.xiaoxue-product：enabled + 只读时写 tools.include 白名单
- platform_toolsets.feishu：加/减 "xiaoxue-product"，开时去掉 "no_mcp"
改完需要重启该 profile 的网关才生效，脚本会提示。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

HERMES_HOME = Path("/home/ubuntu/.hermes")
SERVER_NAME = "xiaoxue-product"
SERVER_COMMAND = "/home/ubuntu/xiaoxue-web/.venv-mcp/bin/python"
SERVER_SCRIPT = "/home/ubuntu/xiaoxue-web/scripts/hermes/xiaoxue_product_mcp.py"

READONLY_TOOLS = [
    "xiaoxue_describe_data",
    "xiaoxue_query_data",
    "xiaoxue_query_readonly_api",
    "xiaoxue_get_today",
    "xiaoxue_get_change_basket",
    "xiaoxue_find_schedules",
    "xiaoxue_open_judgment",
    "xiaoxue_discuss_judgment",
    "xiaoxue_get_match_materials",
    "xiaoxue_get_upcoming_preparation",
    "xiaoxue_prepare_match",
    "xiaoxue_get_gol_facts",
    "xiaoxue_get_match_run",
    "xiaoxue_get_active_match_trade",
    "xiaoxue_get_score",
    "xiaoxue_get_champion_context",
    "xiaoxue_get_match_run_review",
    "xiaoxue_search_trading_tk",
    "xiaoxue_get_team",
    "xiaoxue_get_ts_updates",
    "xiaoxue_search_tk",
    "xiaoxue_get_tk_entry",
    "xiaoxue_search_external_news",
    "xiaoxue_search_predictions",
]


def profile_config(profile: str) -> Path:
    if profile == "default":
        return HERMES_HOME / "config.yaml"
    return HERMES_HOME / "profiles" / profile / "config.yaml"


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"找不到配置文件：{path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        import json
        preview = {
            "mcp_servers.xiaoxue-product": (data.get("mcp_servers") or {}).get(SERVER_NAME),
            "platform_toolsets.feishu": (data.get("platform_toolsets") or {}).get("feishu"),
        }
        print("--- 将要改动（dry-run，未落盘）---")
        print(json.dumps(preview, ensure_ascii=False, indent=2, default=str))
        return
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
    backup = path.with_suffix(path.suffix + f".bak-mcp-toggle-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    print(f"已写入 {path}（备份 {backup.name}）")


def status(data: dict) -> str:
    server = (data.get("mcp_servers") or {}).get(SERVER_NAME) or {}
    feishu = ((data.get("platform_toolsets") or {}).get("feishu")) or []
    enabled = bool(server.get("enabled"))
    listed = SERVER_NAME in feishu
    include = ((server.get("tools") or {}).get("include")) or []
    mode = "只读子集" if include else ("全量" if enabled else "未启用")
    return f"server enabled={enabled}，feishu toolsets {'含' if listed else '不含'} {SERVER_NAME}，模式={mode}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="xiaobai / jieyi / default(小雪)")
    parser.add_argument("--on", action="store_true")
    parser.add_argument("--off", action="store_true")
    parser.add_argument("--read-only", action="store_true", help="只开放只读子集（推荐）")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.profile == "default":
        sys.exit("default(小雪) 本来就是正式入口，不需要用这个脚本切换。")

    path = profile_config(args.profile)
    data = load(path)

    if args.status or not (args.on or args.off):
        print(f"{args.profile}: {status(data)}")
        return

    servers = data.setdefault("mcp_servers", {})
    platform_toolsets = data.setdefault("platform_toolsets", {})
    feishu = platform_toolsets.setdefault("feishu", [])

    if args.on:
        server = servers.setdefault(SERVER_NAME, {})
        server.update({
            "command": SERVER_COMMAND,
            "args": [SERVER_SCRIPT],
            "connect_timeout": 10,
            "timeout": 120,
            "enabled": True,
        })
        if args.read_only:
            server["tools"] = {"include": READONLY_TOOLS}
        else:
            server.pop("tools", None)
        if "no_mcp" in feishu:
            feishu.remove("no_mcp")
        if SERVER_NAME not in feishu:
            feishu.append(SERVER_NAME)
    else:
        server = servers.get(SERVER_NAME)
        if server:
            server["enabled"] = False
        if SERVER_NAME in feishu:
            feishu.remove(SERVER_NAME)

    save(path, data, args.dry_run)
    if not args.dry_run:
        mode = "只读子集（写入能力不外借）" if (args.on and args.read_only) else ("全量" if args.on else "已关闭")
        print(f"{args.profile} -> {mode}")
        print(f"生效需要重启该网关：hermes gateway restart --profile {args.profile}")


if __name__ == "__main__":
    main()
