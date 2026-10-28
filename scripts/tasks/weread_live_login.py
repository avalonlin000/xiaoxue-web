#!/usr/bin/env python3
"""微信读书活码登录恢复。

关键点：必须在 xvfb 里保持 Chromium persistent context 活着等待扫码；
不能截图后立刻 close，否则手机确认不会写入稳定 profile。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image
from playwright.async_api import async_playwright
from pyzbar.pyzbar import decode as decode_barcode

USER_DATA = Path(os.environ.get("WEREAD_USER_DATA", "/home/ubuntu/weread-browser-data"))
LEGACY_USER_DATA = Path("/tmp/weread-browser-data")
CHROMIUM = os.environ.get("CHROMIUM", "/snap/bin/chromium")
STATE = Path("/tmp/weread_live_state.json")
FINAL = Path("/tmp/weread_live_final.png")
BRIDGE_STATE = Path("/tmp/weread_login_bridge.json")
BRIDGE_SECRET = Path(os.environ.get(
    "XIAOXUE_WEREAD_BRIDGE_SECRET",
    "/home/ubuntu/.config/xiaoxue/weread_login_bridge_secret",
))
LOGIN_COOKIES = {"wr_vid", "wr_skey", "wr_rt", "wr_pf", "wr_localvid"}


def _new_qr_path() -> Path:
    """Use an immutable filename so CCPocket/Feishu cannot reuse a stale image."""
    return Path(f"/tmp/weread_qr_live_{time.time_ns()}.png")


def _rotate_bridge_secret() -> str:
    token = secrets.token_urlsafe(32)
    BRIDGE_SECRET.parent.mkdir(parents=True, exist_ok=True)
    BRIDGE_SECRET.write_text(token + "\n", encoding="utf-8")
    BRIDGE_SECRET.chmod(0o600)
    return token


def _publish_bridge(uid: str) -> None:
    payload = {
        "uid": uid,
        "confirm_url": f"https://weread.qq.com/web/confirm?uid={uid}",
        "issued_at": time.time(),
        "valid_until": time.time() + 50,
    }
    temporary = BRIDGE_STATE.with_name(f".{BRIDGE_STATE.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(BRIDGE_STATE)


def _clear_bridge() -> None:
    BRIDGE_STATE.unlink(missing_ok=True)


async def _click_login(page) -> None:
    clicked = await page.evaluate(
        """() => {
            const target = Array.from(document.querySelectorAll('a,button'))
                .find(x => (x.textContent || '').trim() === '登录');
            if (!target) return false;
            target.click();
            return true;
        }"""
    )
    if not clicked:
        raise RuntimeError("未找到微信读书登录入口")


async def _find_qr(page):
    for _ in range(30):
        current = page.locator("img.wr_login_modal_qr_img").first
        if await current.count():
            box = await current.bounding_box()
            if box and box.get("width", 0) >= 120 and box.get("height", 0) >= 120:
                return current
        for item in await page.locator("img").all():
            box = await item.bounding_box()
            if box and box.get("width", 0) >= 120 and box.get("height", 0) >= 120:
                src = await item.get_attribute("src") or ""
                if src.startswith("data:image") or "qr" in src.lower():
                    return item
        await page.wait_for_timeout(200)
    raise RuntimeError("登录弹窗已打开，但没有找到二维码")


async def _open_fresh_qr(page):
    """Open the official modal once; its first uid is the active server token."""
    await _click_login(page)
    await page.wait_for_timeout(2500)
    return await _find_qr(page)


def _qr_uid(path: Path) -> str:
    decoded = decode_barcode(Image.open(path))
    if not decoded:
        raise RuntimeError("生成的二维码无法解码，拒绝发送")
    url = decoded[0].data.decode("utf-8")
    uid = parse_qs(urlparse(url).query).get("uid", [""])[0]
    if not uid:
        raise RuntimeError("二维码缺少 uid，拒绝发送")
    return uid


def _request_uid(url: str) -> str:
    return parse_qs(urlparse(url).query).get("uid", [""])[0]


async def _log_login_response(response) -> None:
    if "/api/auth/getLogin" not in response.url:
        return
    try:
        payload = await response.json()
    except Exception:
        payload = {"http_status": response.status, "body": (await response.text())[:300]}
    if isinstance(payload, dict):
        # Never print reusable login credentials into chat/tool logs.
        for secret in ("accessToken", "token", "skey"):
            if secret in payload:
                payload[secret] = "<redacted>"
    print(json.dumps({
        "event": "LOGIN_API_RESPONSE",
        "endpoint": urlparse(response.url).path,
        "http_status": response.status,
        "payload": payload,
    }, ensure_ascii=False), flush=True)


async def _refresh_expired_qr(page):
    """Ask the already-open modal for a new uid after its server token expires."""
    retry = page.locator(".login_dialog_retry_delegate").first
    if not await retry.count():
        retry = page.locator(".wr_login_modal_qr_overlay").first
    if not await retry.count():
        raise RuntimeError("二维码已失效，但没有找到刷新入口")
    await retry.click()
    await page.wait_for_timeout(1200)
    return await _find_qr(page)


def _sync_legacy_profile() -> None:
    """Keep old /tmp path as a compatibility link to the canonical durable profile."""
    try:
        USER_DATA.mkdir(parents=True, exist_ok=True)
        if LEGACY_USER_DATA.exists() or LEGACY_USER_DATA.is_symlink():
            if LEGACY_USER_DATA.is_symlink():
                if LEGACY_USER_DATA.resolve() == USER_DATA:
                    return
                LEGACY_USER_DATA.unlink()
            else:
                shutil.rmtree(LEGACY_USER_DATA, ignore_errors=True)
        LEGACY_USER_DATA.symlink_to(USER_DATA, target_is_directory=True)
    except Exception:
        pass


def _cleanup_stale_singleton(profile_dir: Path) -> None:
    singleton = profile_dir / "SingletonLock"
    if not singleton.exists():
        return
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"ps -ef | grep -F '{profile_dir}' | grep -v grep"],
            text=True,
            capture_output=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return
    except Exception:
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
        path = profile_dir / name
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except Exception:
            pass


def _inside_xvfb() -> bool:
    return bool(os.environ.get("XIAOXUE_WEREAD_XVFB"))


def _reexec_under_xvfb() -> int:
    if _inside_xvfb():
        return -1
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        print(json.dumps({"ok": False, "status": "NO_XVFB", "hint": "install xvfb or run under X server"}, ensure_ascii=False))
        return 2
    cmd = [
        xvfb,
        "-a",
        "--server-args=-screen 0 1280x900x24 -ac",
        sys.executable,
        __file__,
        *sys.argv[1:],
        "--no-xvfb-reexec",
    ]
    return subprocess.call(cmd, env={**os.environ, "XIAOXUE_WEREAD_XVFB": "1"})


async def live_login(
    wait_seconds: int = 240,
    reset: bool = False,
    auto_refresh: bool = False,
) -> int:
    bridge_secret = _rotate_bridge_secret()
    _clear_bridge()
    if reset:
        shutil.rmtree(USER_DATA, ignore_errors=True)
        shutil.rmtree(LEGACY_USER_DATA, ignore_errors=True)
    USER_DATA.parent.mkdir(parents=True, exist_ok=True)
    USER_DATA.mkdir(parents=True, exist_ok=True)
    _sync_legacy_profile()
    _cleanup_stale_singleton(USER_DATA)
    for path in (STATE, FINAL):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        str(USER_DATA),
        headless=False,
        executable_path=CHROMIUM,
        ignore_default_args=["--enable-automation"],
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--lang=zh-CN",
        ],
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1280, "height": 900},
    )
    page = await ctx.new_page()
    page.on("response", lambda response: asyncio.create_task(_log_login_response(response)))
    try:
        await page.goto("https://weread.qq.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        browser_identity = {
            "webdriver": await page.evaluate("navigator.webdriver"),
            "user_agent": await page.evaluate("navigator.userAgent"),
            "languages": await page.evaluate("navigator.languages"),
            "timezone": await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone"),
        }
        if browser_identity["webdriver"]:
            raise RuntimeError("浏览器仍暴露 webdriver=true，拒绝生成会被风控的二维码")
        async with page.expect_request(
            lambda request: "/api/auth/getLoginInfo" in request.url,
            timeout=10000,
        ) as pending_login_request:
            fresh_qr = await _open_fresh_qr(page)
        login_request = await pending_login_request.value
        qr_path = _new_qr_path()
        await fresh_qr.screenshot(path=str(qr_path))
        qr_uid = _qr_uid(qr_path)
        listening_uid = _request_uid(login_request.url)
        if not listening_uid or qr_uid != listening_uid:
            raise RuntimeError(
                f"二维码 uid 与后台监听不一致：qr={qr_uid} listening={listening_uid}"
            )
        _publish_bridge(qr_uid)
        print(json.dumps({
            "ok": True,
            "event": "QR_READY",
            "fresh": True,
            "path": str(qr_path),
            "bytes": qr_path.stat().st_size,
            "uid": qr_uid,
            "backend_listening": True,
            "browser_identity": browser_identity,
            "bridge_ready": True,
            "bridge_token": bridge_secret,
        }, ensure_ascii=False), flush=True)

        for i in range(wait_seconds):
            await page.wait_for_timeout(1000)
            body = await page.evaluate("document.body.innerText || ''")
            cookies = await ctx.cookies()
            names = [c.get("name") for c in cookies]
            state = {
                "event": "POLL",
                "i": i,
                "url": page.url,
                "has_login": "登录" in body,
                "has_bookshelf": "书架" in body,
                "cookies": names,
            }
            STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            if i % 10 == 0:
                print(json.dumps(state, ensure_ascii=False), flush=True)
            if LOGIN_COOKIES.intersection(names) or (("书架" in body or "我的" in body) and "登录" not in body):
                await ctx.storage_state(path="/tmp/weread_storage_state.json")
                _clear_bridge()
                _sync_legacy_profile()
                await page.screenshot(path=str(FINAL), full_page=False)
                print(json.dumps({"ok": True, "event": "LOGIN_DETECTED", "cookies": names, "final": str(FINAL)}, ensure_ascii=False), flush=True)
                return 0
            if "二维码已失效" in body:
                if not auto_refresh:
                    print(json.dumps({
                        "ok": False,
                        "event": "QR_EXPIRED",
                        "path": str(qr_path),
                        "uid": qr_uid,
                        "note": "聊天中的图片不会自动更新；本轮停止，必须重新签发并发送。",
                    }, ensure_ascii=False), flush=True)
                    return 4
                async with page.expect_request(
                    lambda request: "/api/auth/getLoginInfo" in request.url,
                    timeout=10000,
                ) as refreshed_login_request:
                    fresh_qr = await _refresh_expired_qr(page)
                login_request = await refreshed_login_request.value
                qr_path = _new_qr_path()
                await fresh_qr.screenshot(path=str(qr_path))
                qr_uid = _qr_uid(qr_path)
                listening_uid = _request_uid(login_request.url)
                if not listening_uid or qr_uid != listening_uid:
                    raise RuntimeError(
                        f"刷新二维码 uid 与后台监听不一致：qr={qr_uid} listening={listening_uid}"
                    )
                _publish_bridge(qr_uid)
                print(json.dumps({
                    "ok": True,
                    "event": "QR_REFRESHED",
                    "fresh": True,
                    "path": str(qr_path),
                    "bytes": qr_path.stat().st_size,
                    "uid": qr_uid,
                    "backend_listening": True,
                }, ensure_ascii=False), flush=True)
        await page.screenshot(path=str(FINAL), full_page=False)
        print(json.dumps({"ok": False, "event": "TIMEOUT", "final": str(FINAL)}, ensure_ascii=False), flush=True)
        return 3
    finally:
        _clear_bridge()
        await ctx.close()
        _sync_legacy_profile()
        await p.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description="微信读书活码登录恢复；保持浏览器活着等待扫码写 cookie")
    ap.add_argument("--wait", type=int, default=240, help="等待扫码秒数，默认 240")
    ap.add_argument("--reset", action="store_true", help="清空稳定 profile 后重新登录；仅在明确要废弃旧登录态时使用")
    ap.add_argument("--auto-refresh", action="store_true", help="二维码过期后自动换码；仅用于有人持续转发最新图片的调试场景")
    ap.add_argument("--no-xvfb-reexec", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.no_xvfb_reexec and not _inside_xvfb():
        rc = _reexec_under_xvfb()
        if rc >= 0:
            return rc
    return asyncio.run(
        live_login(
            wait_seconds=args.wait,
            reset=args.reset,
            auto_refresh=args.auto_refresh,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
