#!/usr/bin/env python3
"""
微信读书搜一搜 → 公众号文章链接提取
用法: python3 weread_search.py "关键词" -n 100 --json > /tmp/urls.json
依赖: playwright, 微信读书已登录 (/home/ubuntu/weread-browser-data 持久化)
"""
import asyncio, json, os, sys, re, argparse, shutil, subprocess
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

USER_DATA = Path(os.environ.get("WEREAD_USER_DATA", "/home/ubuntu/weread-browser-data"))
LEGACY_USER_DATA = Path("/tmp/weread-browser-data")
CHROMIUM = os.environ.get("CHROMIUM", "/snap/bin/chromium")


def ensure_profile_paths():
    USER_DATA.mkdir(parents=True, exist_ok=True)
    try:
        if LEGACY_USER_DATA.is_symlink():
            if LEGACY_USER_DATA.resolve() == USER_DATA:
                return
            LEGACY_USER_DATA.unlink()
        elif LEGACY_USER_DATA.exists():
            shutil.rmtree(LEGACY_USER_DATA, ignore_errors=True)
        LEGACY_USER_DATA.symlink_to(USER_DATA, target_is_directory=True)
    except Exception:
        pass


def cleanup_stale_singleton():
    singleton = USER_DATA / "SingletonLock"
    if not singleton.exists():
        return
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"ps -ef | grep -F '{USER_DATA}' | grep -v grep"],
            text=True,
            capture_output=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return
    except Exception:
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
        path = USER_DATA / name
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except Exception:
            pass

async def search_and_extract(query: str, target_count: int = 100, max_scrolls: int = 20):
    ensure_profile_paths()
    cleanup_stale_singleton()
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=True,
            executable_path=CHROMIUM,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()

        # Navigate to search page
        search_url = (
            "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump"
            f"?path=page/search/weread&query={quote(query)}&platform=pc"
        )
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)

        # Check initial count
        count = await page.evaluate('document.querySelectorAll(".search_list_item").length')
        if count == 0:
            print(f"WARNING: 0 results for '{query}'", file=sys.stderr)
            await context.close()
            return []

        # Scroll to load more
        prev, prev2 = 0, 0
        for r in range(max_scrolls):
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight); window.dispatchEvent(new Event('scroll'))")
                await asyncio.sleep(2)
            await asyncio.sleep(2)
            
            count = await page.evaluate('document.querySelectorAll(".search_list_item").length')
            
            # Check "暂无更多内容"
            nomore = await page.evaluate('document.body.textContent.includes("暂无更多内容")')
            if nomore:
                break
            # Check plateau
            if count == prev == prev2 and r > 2:
                break
            # Cap at 500
            if count > 500:
                break
            prev2 = prev
            prev = count

        # Extract article metadata
        articles = await page.evaluate("""() => {
            const arts = [];
            document.querySelectorAll('.search_list_item').forEach((item, i) => {
                const t = item.querySelector('.article__title-text');
                const d = item.querySelector('.article__desc');
                const s = item.querySelector('.source__title');
                const dt = item.querySelector('.source__text.date');
                arts.push({
                    idx: i,
                    title: (t?.textContent || '').trim(),
                    desc: (d?.textContent || '').trim().substring(0, 200),
                    source: (s?.textContent || '').trim(),
                    date: (dt?.textContent || '').trim(),
                    dataId: item.getAttribute('data-id') || ''
                });
            });
            return arts;
        }""")

        # Extract URLs by clicking and intercepting window.open
        js_extract = """async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const items = document.querySelectorAll('.search_list_item');
            const results = [];
            const orig = window.open;
            
            for (let i = 0; i < items.length; i++) {
                let captured = '';
                window.open = function(u) { captured = u; };
                items[i].scrollIntoView({block: 'center', behavior: 'instant'});
                items[i].click();
                await sleep(80);
                results.push({idx: i, url: captured});
            }
            window.open = orig;
            return JSON.stringify(results);
        }"""

        urls_raw = await page.evaluate(js_extract)
        urls_map = {}
        for item in json.loads(urls_raw) if isinstance(urls_raw, str) else urls_raw:
            urls_map[item['idx']] = item['url']

        # Merge
        for art in articles:
            art['url'] = urls_map.get(art['idx'], '')
            del art['idx']
            del art['dataId']

        await context.close()
        return articles[:target_count]


def main():
    parser = argparse.ArgumentParser(description='微信读书公众号文章搜索')
    parser.add_argument('query', help='搜索关键词')
    parser.add_argument('-n', '--count', type=int, default=100, help='目标数量')
    parser.add_argument('--json', action='store_true', help='JSON输出')
    parser.add_argument('--urls-only', action='store_true', help='只输出URL列表')
    args = parser.parse_args()

    articles = asyncio.run(search_and_extract(args.query, args.count))

    if args.urls_only:
        for a in articles:
            if a['url']:
                print(a['url'])
    elif args.json:
        json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
    else:
        succ = sum(1 for a in articles if a['url'])
        print(f"搜到 {len(articles)} 篇 → {succ} 篇有链接（成功率 {100*succ//max(len(articles),1)}%）")
        for i, a in enumerate(articles[:10], 1):
            url = a.get('url', '')
            print(f"{i}. [{a['title']}]({url}) — {a['date']} | {a['source']}")

if __name__ == "__main__":
    main()
