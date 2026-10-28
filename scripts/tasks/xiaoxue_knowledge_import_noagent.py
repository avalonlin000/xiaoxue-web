#!/usr/bin/env python3
"""No-agent Xiaoxue knowledge-import cron entry with a concise audit receipt."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path("/home/ubuntu/lol_data")
EXECUTOR = ROOT / "scripts" / "apply_knowledge_import.py"


def _source_line(name: str, value: Any) -> str:
    data = value if isinstance(value, dict) else {}
    return (
        f"| {name} | {data.get('status', 'unknown')} | {data.get('discovered', 0)} | "
        f"{data.get('processed', 0)} | {data.get('written', 0)} | {data.get('duplicates', 0)} | "
        f"{data.get('failed', 0)} | {data.get('pending_index', 0)} |"
    )


def render_receipt(receipt: dict[str, Any], *, exit_code: int) -> str:
    sources = receipt.get("sources") if isinstance(receipt.get("sources"), dict) else {}
    reindex = receipt.get("reindex") if isinstance(receipt.get("reindex"), dict) else {}
    errors = receipt.get("source_errors") if isinstance(receipt.get("source_errors"), list) else []
    lines = [
        "# 小雪知识导入回执",
        "",
        f"- 时间：{receipt.get('generated_at', '') or '未生成 receipt'}",
        f"- 总状态：{receipt.get('status', 'failed')}",
        f"- 退出码：{exit_code}",
        f"- 索引：{reindex.get('status', 'unknown')}",
        "",
        "| 来源 | 状态 | 发现 | 处理 | 写入 | 重复 | 失败 | 待索引 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        _source_line("B站", sources.get("bilibili")),
        _source_line("公众号", sources.get("wechat")),
    ]
    if errors:
        lines += ["", "## 待恢复"]
        for item in errors:
            if isinstance(item, dict):
                lines.append(f"- {item.get('source', 'unknown')}：{item.get('error', 'unknown error')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    today = date.today().isoformat()
    manifest = ROOT / "scripts" / f"knowledge_import_manifest_{today}.json"
    receipt = ROOT / "scripts" / f"knowledge_import_manifest_{today}-receipt.json"
    if not EXECUTOR.is_file():
        print(f"# 小雪知识导入回执\n\n- 总状态：failed\n- 原因：执行器不存在：{EXECUTOR}\n")
        return 2
    proc = subprocess.run(
        [sys.executable, str(EXECUTOR), "--source", "all"],
        cwd=str(ROOT), text=True, capture_output=True,
    )
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"status": "failed", "source_errors": [{"source": "executor", "error": "receipt missing or invalid"}]}
    print(render_receipt(payload, exit_code=proc.returncode), end="")
    return proc.returncode


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_knowledge_import_noagent.py（无参数；执行双源知识导入）")
        raise SystemExit(0)
    raise SystemExit(main())
