"""用 CDP 驱动一个真实 Chromium：打开足球页、点玩法切换、读回页面文字。

只用于本地验证页面是否真的给出筛选结果，不写入任何业务数据。
"""
import asyncio
import json
import subprocess
import sys
import time
import urllib.request

import websockets

PORT = 9333
URL = "http://127.0.0.1:8880/#football"


def chrome():
    return subprocess.Popen([
        "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--remote-debugging-port={PORT}", "--window-size=1400,1400",
        "--user-data-dir=/tmp/fb-chrome-profile", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main():
    proc = chrome()
    try:
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("chrome 未就绪")
            return 1
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
            counter = 0

            async def call(method, **params):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == counter:
                        return msg.get("result", {})

            async def evaluate(expr):
                result = await call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return result.get("result", {}).get("value")

            await call("Page.enable")
            await call("Runtime.enable")
            await call("Page.navigate", url=URL)
            await asyncio.sleep(4)

            async def summary():
                return await evaluate("""(() => {
                  const s = document.querySelector('[data-football-summary]');
                  const cards = Array.from(document.querySelectorAll('.football-list .football-match-card'));
                  const first = cards[0];
                  const tabs = Array.from(document.querySelectorAll('[data-football-play]')).map(b => b.textContent.trim() + (b.classList.contains('active') ? '*' : ''));
                  return JSON.stringify({
                    tabs,
                    summary: s ? s.textContent.trim() : null,
                    cards: cards.length,
                    firstCard: first ? first.innerText.replace(/\\s+/g, ' ').slice(0, 160) : null,
                    empty: document.querySelector('.football-list .football-empty')?.textContent?.trim() || null,
                  });
                })()""")

            print("全部:", await summary())
            for play in ("half_break", "late_over"):
                await evaluate(f"""(() => {{
                  const b = document.querySelector('[data-football-play="{play}"]');
                  if (b) b.click();
                  return true;
                }})()""")
                await asyncio.sleep(1.5)
                print(f"{play}:", await summary())

            # 打开第一场详情，确认两种玩法依据都显示
            await evaluate("""(() => {
              document.querySelector('[data-football-play="all"]')?.click();
              return true;
            })()""")
            await asyncio.sleep(1.5)
            await evaluate("""(() => {
              const b = document.querySelector('.football-list [data-football-action="details"]');
              if (b) b.click();
              return true;
            })()""")
            await asyncio.sleep(4)
            print("详情:", await evaluate("""(() => {
              const d = document.querySelector('.football-detail');
              return d ? d.innerText.replace(/\\s+/g, ' ').slice(0, 400) : 'NO DETAIL';
            })()"""))
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
