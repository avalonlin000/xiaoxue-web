#!/usr/bin/env python3
"""微信读书登录态检查与二维码发送。

用于小雪知识导入自动化：
- --check: 检查稳定 profile 是否仍登录
- --send-qr: 登录过期时截取二维码并通过飞书私聊发给钧钧

不要把二维码转成代码/base64 输出给用户；直接发图片附件。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

USER_DATA = Path(os.environ.get("WEREAD_USER_DATA", "/home/ubuntu/weread-browser-data"))
LEGACY_USER_DATA = Path("/tmp/weread-browser-data")
QR_PATH = Path("/tmp/weread_qr.png")
DEBUG_PATH = Path("/tmp/weread_debug.png")
CHROMIUM = os.environ.get("CHROMIUM", "/snap/bin/chromium")
JUNJUN_DM_CHAT_ID = "oc_ea3e8a94e605b314217400fddc335ef9"


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 45) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True, capture_output=True)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout: {exc}"


def _ensure_legacy_profile_link() -> None:
    """Keep the old /tmp path pointing at the canonical durable profile."""
    try:
        USER_DATA.mkdir(parents=True, exist_ok=True)
        if LEGACY_USER_DATA.is_symlink():
            if LEGACY_USER_DATA.resolve() == USER_DATA:
                return
            LEGACY_USER_DATA.unlink()
        elif LEGACY_USER_DATA.exists():
            shutil.rmtree(LEGACY_USER_DATA, ignore_errors=True)
        LEGACY_USER_DATA.symlink_to(USER_DATA, target_is_directory=True)
    except Exception:
        # The check itself can still use USER_DATA; legacy compatibility is best-effort.
        pass


def _cleanup_stale_singleton(profile_dir: Path) -> None:
    """Remove Chromium singleton files only when no process owns this profile."""
    singleton = profile_dir / "SingletonLock"
    if not singleton.exists():
        return
    code, out = _run(["bash", "-lc", f"ps -ef | grep -F '{profile_dir}' | grep -v grep"], timeout=5)
    if code == 0 and out.strip():
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
        path = profile_dir / name
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


async def _open_context():
    p = await async_playwright().start()
    _ensure_legacy_profile_link()
    profile_dir = USER_DATA
    _cleanup_stale_singleton(profile_dir)
    ctx = await p.chromium.launch_persistent_context(
        str(profile_dir),
        headless=True,
        executable_path=CHROMIUM,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        viewport={"width": 1280, "height": 900},
    )
    return p, ctx


async def check_login() -> dict:
    p, ctx = await _open_context()
    page = await ctx.new_page()
    try:
        await page.goto("https://weread.qq.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        body = await page.evaluate("document.body.innerText || ''")
        has_login = await page.evaluate(
            "Array.from(document.querySelectorAll('a,button')).some(x => (x.textContent||'').includes('登录'))"
        )
        logged_in = (not has_login) and any(token in body for token in ("书架", "继续", "微信读书", "排行榜"))
        return {"ok": True, "logged_in": bool(logged_in), "status": "OK" if logged_in else "NEED_LOGIN"}
    except Exception as exc:
        return {"ok": False, "logged_in": False, "status": "ERROR", "error": repr(exc)}
    finally:
        await ctx.close()
        await p.stop()


async def capture_qr() -> dict:
    p, ctx = await _open_context()
    page = await ctx.new_page()
    try:
        await page.goto("https://weread.qq.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        # If already logged in, no QR needed. Do this in the same context;
        # opening a second persistent context on USER_DATA trips Chromium's
        # ProcessSingleton lock.
        body = await page.evaluate("document.body.innerText || ''")
        has_login = await page.evaluate(
            "Array.from(document.querySelectorAll('a,button')).some(x => (x.textContent||'').includes('登录'))"
        )
        if (not has_login) and any(token in body for token in ("书架", "继续", "微信读书", "排行榜")):
            return {"ok": True, "status": "ALREADY_LOGGED_IN", "path": None}

        # Click 登录 if visible. Use several selectors/text paths because WeRead changes markup.
        clicked = False
        for selector in ["text=登录", "a:has-text('登录')", "button:has-text('登录')"]:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    await loc.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            await page.evaluate("Array.from(document.querySelectorAll('a,button')).find(x => (x.textContent||'').includes('登录'))?.click()")
        await page.wait_for_timeout(5000)

        # Prefer screenshot of the visible QR image; fallback to full viewport.
        qr = None
        for selector in ["img[src*='qrcode']", "img"]:
            try:
                candidates = await page.locator(selector).all()
                for item in candidates:
                    box = await item.bounding_box()
                    if box and box.get("width", 0) >= 120 and box.get("height", 0) >= 120:
                        qr = item
                        break
                if qr:
                    break
            except Exception:
                pass
        if qr:
            await qr.screenshot(path=str(QR_PATH))
        else:
            await page.screenshot(path=str(QR_PATH), full_page=False)
        if not QR_PATH.exists() or QR_PATH.stat().st_size < 1000:
            await page.screenshot(path=str(DEBUG_PATH), full_page=True)
            return {"ok": False, "status": "QR_CAPTURE_FAILED", "debug": str(DEBUG_PATH)}
        return {"ok": True, "status": "QR_CAPTURED", "path": str(QR_PATH), "bytes": QR_PATH.stat().st_size}
    except PlaywrightTimeoutError as exc:
        return {"ok": False, "status": "TIMEOUT", "error": repr(exc)}
    except Exception as exc:
        try:
            await page.screenshot(path=str(DEBUG_PATH), full_page=True)
        except Exception:
            pass
        return {"ok": False, "status": "ERROR", "error": repr(exc), "debug": str(DEBUG_PATH)}
    finally:
        await ctx.close()
        await p.stop()


def send_qr_to_feishu() -> dict:
    if not QR_PATH.exists():
        return {"ok": False, "error": f"QR not found: {QR_PATH}"}
    cmd = [
        "lark-cli", "im", "+messages-send",
        "--as", "user",
        "--chat-id", JUNJUN_DM_CHAT_ID,
        "--image", f"./{QR_PATH.name}",
        "--format", "json",
    ]
    code, out = _run(cmd, cwd=str(QR_PATH.parent), timeout=60)
    try:
        parsed = json.loads(out[out.find("{"):]) if "{" in out else {"raw": out}
    except Exception:
        parsed = {"raw": out}
    return {"ok": code == 0 and bool(parsed.get("ok", True)), "exit_code": code, "response": parsed}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--send-qr", action="store_true")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON for --send-qr instead of human-safe status text")
    args = ap.parse_args()

    if args.send_qr:
        cap = await capture_qr()
        if not cap.get("ok"):
            print(json.dumps(cap, ensure_ascii=False))
            return 2
        if cap.get("status") == "ALREADY_LOGGED_IN":
            print(json.dumps(cap, ensure_ascii=False))
            return 0
        sent = send_qr_to_feishu()
        result = {"capture": cap, "send": sent}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif sent.get("ok"):
            print("二维码已发")
        else:
            print(f"二维码发送失败，交给小白处理：path={cap.get('path')} error={json.dumps(sent, ensure_ascii=False)}")
        return 0 if sent.get("ok") else 3

    result = await check_login()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
