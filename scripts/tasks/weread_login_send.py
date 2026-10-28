#!/usr/bin/env python3
"""启动微信读书活码登录，并把最新二维码发送到飞书私聊。

用法: python3 weread_login_send.py [等待秒数，默认300]
二维码发出后保持浏览器活着，扫码确认时输出 LOGIN_DETECTED 才算成功。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

CHAT_ID = "oc_ea3e8a94e605b314217400fddc335ef9"
LIVE = Path(__file__).resolve().with_name("weread_live_login.py")


def main() -> int:
    wait = sys.argv[1] if len(sys.argv) > 1 else "300"
    log = Path(f"/tmp/weread_login_{int(time.time())}.log")
    proc = subprocess.Popen(
        [sys.executable, str(LIVE), "--wait", wait],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    sent = False
    try:
        with log.open("w", encoding="utf-8") as fh:
            for line in proc.stdout:
                fh.write(line)
                fh.flush()
                stripped = line.strip()
                if stripped.startswith("{") and '"QR_READY"' in stripped and not sent:
                    data = json.loads(stripped)
                    path = data.get("path", "")
                    res = subprocess.run(
                        [
                            "lark-cli", "im", "+messages-send",
                            "--as", "user",
                            "--chat-id", CHAT_ID,
                            "--image", f"./{Path(path).name}",
                            "--format", "json",
                        ],
                        cwd=str(Path(path).parent),
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    ok = res.returncode == 0
                    print(f"二维码发送{'成功' if ok else '失败'}: {path}", flush=True)
                    if not ok:
                        print((res.stdout or "")[-300:], (res.stderr or "")[-300:], flush=True)
                    sent = True
                if any(k in stripped for k in ('"LOGIN_DETECTED"', '"TIMEOUT"', '"QR_EXPIRED"', '"ERROR"')):
                    print(stripped, flush=True)
                    break
    finally:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    print(f"日志: {log}", flush=True)
    return 0 if sent else 1


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("用法：weread_login_send.py [等待秒数]（会打开登录页并发送二维码）")
        raise SystemExit(0)
    raise SystemExit(main())
