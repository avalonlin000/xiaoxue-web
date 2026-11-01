"""只验证详情打开：点第一场「查看详情」，读回详情内容。"""
import asyncio
import json
import subprocess
import sys
import time
import urllib.request

import websockets

PORT = 9334
URL = "http://127.0.0.1:8880/#football"


async def main():
    proc = subprocess.Popen([
        "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--remote-debugging-port={PORT}", "--window-size=1400,1400",
        "--user-data-dir=/tmp/fb-chrome-profile2", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
            counter = 0
            logs = []

            async def call(method, **params):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == counter:
                        return msg.get("result", {})
                    if msg.get("method") in {"Runtime.consoleAPICalled", "Log.entryAdded"}:
                        logs.append(msg)

            async def evaluate(expr):
                res = await call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return res.get("result", {}).get("value")

            await call("Page.enable")
            await call("Runtime.enable")
            await call("Log.enable")
            await call("Page.navigate", url=URL)
            await asyncio.sleep(5)
            print("cards:", await evaluate("document.querySelectorAll('.football-list .football-match-card').length"))
            print("click:", await evaluate("""(() => {
              const b = document.querySelector('.football-list [data-football-action="details"]');
              if (!b) return 'no button';
              b.click();
              return 'clicked ' + b.dataset.matchId;
            })()"""))
            for _ in range(12):
                await asyncio.sleep(2)
                text = await evaluate("(() => { const d = document.querySelector('.football-detail'); return d ? d.innerText.replace(/\\s+/g,' ').slice(0,300) : null; })()")
                if text:
                    print("详情:", text)
                    return 0
            print("详情未出现; 控制台日志:", [l for l in logs][:5])
            return 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
