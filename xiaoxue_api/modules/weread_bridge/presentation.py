from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import service


router = APIRouter(prefix="/auth/weread", tags=["weread-bridge"])

CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _resolve(token: str) -> str | None:
    try:
        return service.resolve(token)
    except service.BridgeNotFound as exc:
        raise HTTPException(404, "页面不存在") from exc


@router.get("/current")
def current(token: str = Query(default="")):
    confirm_url = _resolve(token)
    if not confirm_url:
        return JSONResponse(
            {"ready": False},
            status_code=202,
            headers=CACHE_HEADERS,
        )
    return JSONResponse(
        {"ready": True, "url": confirm_url},
        headers=CACHE_HEADERS,
    )


@router.get("")
def bridge(token: str = Query(default="")):
    confirm_url = _resolve(token)
    if confirm_url:
        return RedirectResponse(
            confirm_url,
            status_code=302,
            headers=CACHE_HEADERS,
        )

    token_json = json.dumps(token)
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信读书登录</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px 20px">
<h2>正在获取最新登录请求…</h2><p>请保持本页打开，无需重新扫码。</p>
<script>
const token = {token_json};
async function followLatest() {{
  try {{
    const response = await fetch('/auth/weread/current?token=' + encodeURIComponent(token), {{cache:'no-store'}});
    if (response.ok) {{
      const data = await response.json();
      if (data.ready && data.url) {{ location.replace(data.url); return; }}
    }}
  }} catch (_) {{}}
  setTimeout(followLatest, 700);
}}
followLatest();
</script></body></html>"""
    return HTMLResponse(html, headers=CACHE_HEADERS)
