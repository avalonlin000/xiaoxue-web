#!/usr/bin/env python3
"""微信读书批量搜索：一次启动浏览器，循环多个关键词，只取首屏结果（不滚动）。

给历史公众号补导用：按标题回查真实 mp.weixin.qq.com 链接。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.tasks.knowledge.wechat_scripts.weread_search import (  # noqa: E402
    CHROMIUM,
    USER_DATA,
    cleanup_stale_singleton,
    ensure_profile_paths,
)
from playwright.async_api import async_playwright  # noqa: E402

EXTRACT_JS = """() => {
    const out = [];
    document.querySelectorAll('.search_list_item').forEach((item, i) => {
        const t = item.querySelector('.article__title-text');
        const d = item.querySelector('.article__desc');
        const s = item.querySelector('.source__title');
        const dt = item.querySelector('.source__text.date');
        out.push({idx: i, title: (t?.textContent || '').trim(),
                  desc: (d?.textContent || '').trim().substring(0, 200),
                  source: (s?.textContent || '').trim(),
                  date: (dt?.textContent || '').trim()});
    });
    return out.slice(0, 8);
}"""

CLICK_JS = """async (n) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const items = document.querySelectorAll('.search_list_item');
    const res = [];
    const orig = window.open;
    for (let i = 0; i < Math.min(n, items.length); i++) {
        let cap = '';
        window.open = function (u) { cap = u; };
        items[i].scrollIntoView({block: 'center', behavior: 'instant'});
        items[i].click();
        await sleep(80);
        res.push({idx: i, url: cap});
    }
    window.open = orig;
    return JSON.stringify(res);
}"""


async def batch_search(queries: list[str], per_query: int = 4) -> dict:
    ensure_profile_paths()
    cleanup_stale_singleton()
    results: dict[str, list] = {}
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=True,
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        for index, query in enumerate(queries, 1):
            try:
                url = ("https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump"
                       f"?path=page/search/weread&query={quote(query)}&platform=pc")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                articles = await page.evaluate(EXTRACT_JS)
                raw = await page.evaluate(CLICK_JS, per_query)
                url_map = {row["idx"]: row["url"] for row in json.loads(raw)}
                for article in articles:
                    article["url"] = url_map.get(article["idx"], "")
                    article.pop("idx", None)
                results[query] = articles
                hit = sum(1 for a in articles if "mp.weixin.qq.com" in (a.get("url") or ""))
                print(f"[{index}/{len(queries)}] {query[:28]} → {len(articles)} 条（{hit} 有链接）", flush=True)
            except Exception as exc:  # noqa: BLE001
                results[query] = []
                print(f"[{index}/{len(queries)}] {query[:28]} → ERR {type(exc).__name__}", flush=True)
            await asyncio.sleep(1.2)
        await context.close()
    return results


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("queries_file", help="每行一个搜索词")
    ap.add_argument("-o", "--output", default="/tmp/weread_batch.json")
    ap.add_argument("-n", "--per-query", type=int, default=4)
    args = ap.parse_args()
    queries = [line.strip() for line in Path(args.queries_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"共 {len(queries)} 个搜索词", flush=True)
    started = time.time()
    results = await batch_search(queries, args.per_query)
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成 {len(results)} 个，用时 {time.time() - started:.0f}s → {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
