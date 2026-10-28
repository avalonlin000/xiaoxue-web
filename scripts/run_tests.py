#!/usr/bin/env python3
"""Run the test surface split across the project's own Python environments.

The workbench API, TK adapter and Feishu product MCP run on separate Python
versions with pinned dependencies. Each test file runs in the environment that
owns its runtime instead of leaking another tool's site-packages into pytest.
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
    or ROOT / ".venv-mcp" / "bin" / "python"
)
MCP_TEST_FILES = (
    "tests/test_xiaoxue_product_mcp.py",
    "tests/test_xiaoxue_prepared_reader_mcp.py",
)
TK_PYTHON = Path(
    os.environ.get("XIAOXUE_TK_PYTHON")
    or ROOT / ".venv-tk" / "bin" / "python"
)
TK_TEST_FILES = ("tests/test_mempalace_tk_adapter.py",)


def run(label: str, command: list[str]) -> tuple[bool, str]:
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), text=True)
    return completed.returncode == 0, label


def main() -> int:
    node_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("*.test.mjs"))
    node = shutil.which("node") or "node"
    steps = [("前端测试", [node, "--test", *node_tests])]

    isolated_tests = MCP_TEST_FILES + TK_TEST_FILES
    ignores = [f"--ignore={path}" for path in isolated_tests]
    steps.append(("工作台后端测试", [sys.executable, "-m", "pytest", "tests", "-q", *ignores]))

    if TK_PYTHON.is_file():
        steps.append(("TK 测试", [str(TK_PYTHON), "-m", "pytest", *TK_TEST_FILES, "-q"]))
    else:
        print(f"\n跳过 TK 测试：找不到 {TK_PYTHON}")

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
