#!/usr/bin/env python3
"""no-agent 排程器入口：调用唯一排程器，成功静默，异常出声。

排程器是 LOL 自动化的唯一时间正源；执行时刻由赛程算出，人不改钟点。
"""
from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

TARGET = Path("/home/ubuntu/lol_data/scripts/lol_auto_planner.py")


def prepare_materials() -> int:
    """Enqueue/check through the original CLI; it dispatches, never waits for a batch.

    This wrapper does not publish or notify. The current Hermes job remains the
    single scheduling entry; changing its interval is a separate activation step.
    """
    sys.path.insert(0, str(TARGET.parent.parent / "libs"))
    from config import SYSTEM_CONFIG_PATH
    config = json.loads(SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))
    root = (config.get("paths") or {}).get("xiaoxue_web_root")
    if not root:
        raise ValueError("工作台路径未配置")
    entry = Path(root) / "scripts" / "collect_match_materials.py"
    if not entry.is_file():
        raise ValueError("准备入口不可读")
    result = subprocess.run([sys.executable, str(entry), "--scheduler-tick"],
                            cwd=str(entry.parent.parent), capture_output=True, text=True, timeout=90)
    return result.returncode


def main() -> int:
    # Preparation remains independent of a terminal pre/post notification job.
    try:
        preparation_status = prepare_materials()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        preparation_status = 2
    if preparation_status:
        print("⚠️ LOL 后台准备检查未完成，已有成果保留。")
    if not TARGET.is_file():
        print(f"❌ 排程器缺失：{TARGET}")
        return 2
    result = subprocess.run([sys.executable, str(TARGET)], capture_output=True, text=True, cwd=str(TARGET.parent))
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        print("❌ LOL 自动化排程失败")
        print(output[:1500] or (result.stderr or "")[:1500])
        return result.returncode
    if any(marker in output for marker in ("失败", "未就绪", "读不到")):
        print("⚠️ LOL 自动化排程未完全生效")
        print(output[:1500])
        return 0
    return preparation_status


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：xiaoxue_auto_plan.py（无参数；执行 LOL 自动化排程）")
        raise SystemExit(0)
    raise SystemExit(main())
