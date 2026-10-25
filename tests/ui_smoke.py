import os

from playwright.sync_api import sync_playwright


URL = os.environ.get("XIAOXUE_TEST_URL", "http://127.0.0.1:8880/")


def visible_text(page):
    return page.locator("body").inner_text()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path="/snap/bin/chromium",
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    failed_responses = []
    page_errors = []
    page.on(
        "response",
        lambda response: failed_responses.append((response.status, response.url))
        if response.status >= 400 and not response.url.endswith("/favicon.ico")
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(URL)
    page.wait_for_load_state("networkidle")

    tabs = page.locator(".workspace-tab").all_inner_texts()
    assert tabs == ['队伍资料', '当前赛事', '沉淀候选', '足球', 'TK资料库', '项目中心'], tabs
    assert page.get_by_role("button", name="队伍资料", exact=True).get_attribute("class").find("active") >= 0
    teams = visible_text(page)
    assert "队伍资料" in teams
    assert page.locator("#fundamentals-table .fund-row").count() > 0
    assert page.locator("#col-profile").is_hidden()
    page.screenshot(path="/tmp/xiaoxue-teams-overview.png", full_page=True)

    page.get_by_role("button", name="当前赛事", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('#event-match-list').innerText.length > 0",
        timeout=10_000,
    )
    event = visible_text(page)
    assert page.locator("#event-match-list .event-match-button").count() >= 0
    assert "今天的比赛" in event
    if page.locator("#event-match-list .event-match-button").count():
        page.locator("#event-match-list .event-match-button").first.click()
        page.wait_for_function(
            "() => document.querySelector('#event-match-desk').innerText.length > 0",
            timeout=10_000,
        )
        assert "TS：" in page.locator("#event-match-desk").inner_text()
    page.screenshot(path="/tmp/xiaoxue-event.png", full_page=True)

    page.get_by_role("button", name="阶段整理", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('#stage-review-summary').innerText.includes('正在读取')",
        timeout=10_000,
    )
    assert page.locator("#card-stage-review").is_visible()
    page.screenshot(path="/tmp/xiaoxue-stage-review.png", full_page=True)

    page.get_by_role("button", name="队伍资料", exact=True).click()
    page.locator("#fundamentals-table .fund-row[data-team]").first.click()
    page.wait_for_timeout(300)
    assert page.locator("#col-profile").is_visible()

    page.get_by_role("button", name="TK资料库", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('#tk-library-results').innerText.includes('读取中')",
        timeout=10_000,
    )
    assert page.locator("#card-tk-library").is_visible()
    assert "2026-07" in page.locator("#tk-library-results").inner_text()
    page.screenshot(path="/tmp/xiaoxue-tk-library.png", full_page=True)
    page.locator(".tk-library-open").first.click()
    page.wait_for_function(
        "() => document.querySelector('#tk-reader-content').innerText.length > 100",
        timeout=10_000,
    )
    assert page.locator("#tk-reader-overlay").is_visible()
    page.screenshot(path="/tmp/xiaoxue-tk-reader.png", full_page=True)
    page.get_by_role("button", name="关闭全文", exact=True).click()

    page.locator('[data-shell-action="open-market-helper"]').click()
    page.wait_for_timeout(300)
    assert page.locator("#card-trades").is_visible()
    assert page.locator(".workspace-tab").count() == 4

    if page.locator("#trade-list .trade-item").count():
        page.locator("#trade-list .trade-item").first.get_by_role("button", name="复盘", exact=True).click()
        assert page.locator("#market-review-panel").is_visible()

    page.screenshot(path="/tmp/xiaoxue-market-helper.png", full_page=True)
    assert not failed_responses, failed_responses
    assert not page_errors, page_errors
    browser.close()
