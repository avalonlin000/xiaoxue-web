#!/usr/bin/env python3
"""Run the whole test surface, including the product MCP server's own venv.

The workbench API and the Feishu product MCP server run in different Python
environments (the MCP server pins fastmcp + mcp 1.x, Hermes pins mcp 2.x), so
one interpreter cannot import both. This runner keeps a single command honest
instead of letting a missing dependency look like a failing test.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MCP_PYTHON = Path(
    os.environ.get("XIAOXUE_MCP_PYTHON")
    or "/home/ubuntu/.hermes/venvs/xiaoxue-product-mcp/bin/python"
)
MCP_TEST_FILES = (
    "tests/test_xiaoxue_product_mcp.py",
    "tests/test_xiaoxue_prepared_reader_mcp.py",
)


def run(label: str, command: list[str]) -> tuple[bool, str]:
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), text=True)
    return completed.returncode == 0, label


def main() -> int:
    node_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("*.test.mjs"))
    node = shutil.which("node") or "node"
    steps = [("前端测试", [node, "--test", *node_tests])]

    keep_mcp = f"--ignore={MCP_TEST_FILES[0]}"
    keep_mcp_2 = f"--ignore={MCP_TEST_FILES[1]}"
    steps.append(("工作台后端测试", [sys.executable, "-m", "pytest", "tests", "-q", keep_mcp, keep_mcp_2]))

    if MCP_PYTHON.is_file():
        steps.append(("产品 MCP 测试", [str(MCP_PYTHON), "-m", "pytest", *MCP_TEST_FILES, "-q"]))
    else:
        print(f"\n跳过产品 MCP 测试：找不到 {MCP_PYTHON}")

    results = [run(label, command) for label, command in steps]
    failed = [label for ok, label in results if not ok]
    print("\n=== 汇总 ===")
    for ok, label in results:
        print(f"{'通过' if ok else '失败'}  {label}")
    print("全部通过" if not failed else f"有失败项：{', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
