#!/usr/bin/env python3
"""概念关系图更新（no-agent 入口）。

跑 /home/ubuntu/lol_data/scripts/update_tk_graph.sh，成功后读取产物
/home/ubuntu/tk_graph_serve/data.json 输出结构化摘要；失败时输出错误尾部。
cron: 0b3e5e1571db「概念关系图更新」（每天 06:30，deliver=origin）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = "/home/ubuntu/lol_data/scripts/update_tk_graph.sh"
DATA = Path("/home/ubuntu/tk_graph_serve/data.json")
TK_DIR = Path("/home/ubuntu/workspace/knowledge/wiki/小雪电竞/原始资料/tk")


def main() -> int:
    r = subprocess.run(["bash", SCRIPT], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"❌ 概念关系图更新失败（exit={r.returncode}）")
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-10:]
        for line in tail:
            print(line)
        return r.returncode

    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        nodes = data.get("nodes", [])
        links = data.get("links", [])
        idx = data.get("tk_index", {})
        by_type: dict[str, int] = {}
        for n in nodes:
            t = str(n.get("type", "other"))
            by_type[t] = by_type.get(t, 0) + 1
        tk_count = len(list(TK_DIR.glob("*.md")))
        print("✅ 概念关系图更新完成")
        print(f"{tk_count} 条 TK 记录 → {len(nodes)} 节点 / {len(links)} 条连接 / {len(idx)} 个索引标签")
        print(f"节点构成：概念 {by_type.get('concept', 0)}、队伍 {by_type.get('team', 0)}、选手 {by_type.get('player', 0)}")
    except Exception as e:  # 数据文件缺失/损坏时给原始输出兜底
        print(f"⚠️ 脚本已成功，但产物摘要读取失败：{e}")
        print((r.stdout or "").strip()[-400:])
    return 0


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_tk_graph_noagent.py（无参数；更新 TK 概念关系图）")
        raise SystemExit(0)
    sys.exit(main())
