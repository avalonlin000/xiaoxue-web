#!/usr/bin/env python3
"""Retired compatibility entrypoint; no legacy write or secret access is retained."""
import json


def main() -> int:
    print(json.dumps({
        "ok": False,
        "status": "retired_entrypoint",
        "error": "batch_tk_extract.py 已停用；请运行统一 apply_knowledge_import.py",
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
