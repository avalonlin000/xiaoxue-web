#!/usr/bin/env python3
"""小雪菜单 / 引导读取器（项目中心内容正源的唯一出口）

小雪 Skill 的「引导与菜单」和项目总使用说明都不另存功能清单，直接读这里的输出：
项目中心内容（config/project-center-content.json）是唯一正源，内容改了，菜单和模块
说明自动跟着变，不需要同步动作。

用法：
  python3 scripts/xiaoxue_menu.py              # 菜单：每个场景一行「场景 → 示例说法」
  python3 scripts/xiaoxue_menu.py --scenario teams-and-tk   # 单个场景的完整口径
  python3 scripts/xiaoxue_menu.py --modules    # 模块一览：每个一级模块一行
  python3 scripts/xiaoxue_menu.py --module long-term-understanding   # 单个模块的完整口径
只读；读不到时返回非零并给出人话说明，调用方据此给简版。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CONTENT = PROJECT / "config" / "project-center-content.json"
MAX_LINES = 15


def load_source() -> tuple[dict, dict, list[dict], str]:
    payload = json.loads(CONTENT.read_text(encoding="utf-8"))
    manual = payload.get("manual")
    if not isinstance(manual, dict) or not manual.get("sections"):
        raise ValueError("项目中心内容里没有使用说明场景")
    tree = payload.get("module_tree")
    if not isinstance(tree, list) or not tree:
        raise ValueError("项目中心内容里没有模块树")
    return manual, payload, tree, str(payload.get("content_version", ""))


def render_menu(manual: dict, version: str) -> str:
    lines = [f"【我能帮你做的（内容版本 {version}）】"]
    for section in manual["sections"]:
        say = section.get("say") or []
        example = say[0] if say else ""
        lines.append(f"- {section.get('title', '')} → 试试说：{example}")
    extras = manual.get("extras") or []
    if extras:
        lines.append("【说明书之外的常用说法】")
        for group in extras:
            says = " / ".join(group.get("say") or [])
            lines.append(f"- {group.get('label', '')} → {says}")
    return "\n".join(lines)


def render_scenario(manual: dict, scenario_id: str) -> str:
    for section in manual["sections"]:
        if section.get("id") != scenario_id:
            continue
        out = [
            f"场景：{section.get('title', '')}",
            f"此刻做什么：{section.get('what', '')}",
            f"去哪里：{section.get('where', '')}",
            "可以这样说：",
        ]
        out += [f"  - {item}" for item in section.get("say") or []]
        out += [
            f"能得到什么：{section.get('get', '')}",
            f"何时不要这样用：{section.get('not_for', '')}",
        ]
        return "\n".join(out)
    known = "、".join(item.get("id", "") for item in manual["sections"])
    return f"没有这个场景：{scenario_id}（可用：{known}）"


def render_modules(tree: list[dict], version: str) -> str:
    lines = [f"【模块一览（内容版本 {version}）】"]
    for node in tree:
        lines.append(f"- {node.get('name', '')}：{node.get('purpose', '')}")
        lines.append(f"  什么时候用：{node.get('when_to_use', '')}")
    return "\n".join(lines)


def render_module(tree: list[dict], module_id: str) -> str:
    for node in tree:
        if node.get("id") != module_id:
            continue
        children = "、".join(child.get("name", "") for child in node.get("children") or [])
        out = [
            f"模块：{node.get('name', '')}",
            f"用它解决：{node.get('purpose', '')}",
            f"什么时候用：{node.get('when_to_use', '')}",
            f"现在能做什么：{node.get('current_capability', '')}",
            f"边界：{node.get('boundaries', '')}",
            f"下一步：{node.get('next_step', '')}",
        ]
        if children:
            out.append(f"包含能力：{children}")
        return "\n".join(out)
    known = "、".join(node.get("id", "") for node in tree)
    return f"没有这个模块：{module_id}（可用：{known}）"


def main() -> int:
    parser = argparse.ArgumentParser(description="读取项目中心内容里的使用说明与模块树")
    parser.add_argument("--scenario", help="只看一个场景（用场景 id）")
    parser.add_argument("--modules", action="store_true", help="模块一览（一级模块）")
    parser.add_argument("--module", help="只看一个模块（用模块 id）")
    args = parser.parse_args()

    try:
        manual, _content, tree, version = load_source()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"暂时读不到项目中心内容：{exc}", file=sys.stderr)
        return 2

    if args.module:
        print(render_module(tree, args.module))
        return 0
    if args.modules:
        print(render_modules(tree, version))
        return 0
    if args.scenario:
        print(render_scenario(manual, args.scenario))
        return 0

    text = render_menu(manual, version)
    print(text)
    if len(text.splitlines()) > MAX_LINES + 12:
        print("（场景较多时按相近分组再输出，不要照抄全部）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
