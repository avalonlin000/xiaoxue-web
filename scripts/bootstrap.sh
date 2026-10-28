#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
uv venv .venv
uv pip install --python .venv/bin/python -r requirements/dev.txt
uv venv .venv-tk
uv pip install --python .venv-tk/bin/python -r requirements/tk.txt
uv venv .venv-mcp
uv pip install --python .venv-mcp/bin/python -r requirements/mcp.txt
printf '环境已重建。运行 scripts/health_check.py 验收。\n'
