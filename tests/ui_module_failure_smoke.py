import os

from playwright.sync_api import sync_playwright


URL = os.environ.get("XIAOXUE_TEST_URL", "http://127.0.0.1:8880/")
EVENT_PATH = "/api/tk/search?q=EWC"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path="/snap/bin/chromium",
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page_errors = []
    unexpected_failed_responses = []

    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "response",
        lambda response: unexpected_failed_responses.append((response.status, response.url))
        if response.status >= 400
        and EVENT_PATH not in response.url
        and not response.url.endswith("/favicon.ico")
        else None,
    )
    page.route(
        f"**{EVENT_PATH}*",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail":"当前赛事故障隔离验收"}',
        ),
    )

    page.goto(URL)
    page.wait_for_load_state("networkidle")

    page.get_by_role("button", name="当前赛事", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('#card-current-event')?.dataset.moduleStatus === 'broken'",
        timeout=10_000,
    )
    assert "其他窗口可以继续使用" in page.locator("#event-knowledge-results").inner_text()

    page.get_by_role("button", name="队伍资料", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('#fundamentals-table')?.innerText.includes('加载横向基本面中')",
        timeout=10_000,
    )
    assert page.locator("#card-fundamentals").is_visible()
    assert page.locator("#fundamentals-table .fund-row").count() > 0

    page.get_by_role("button", name="TK资料库", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('#tk-library-results')?.innerText.includes('读取中')",
        timeout=10_000,
    )
    assert page.locator("#card-tk-library").is_visible()
    assert page.locator("#tk-library-results .tk-library-card").count() > 0

    assert not unexpected_failed_responses, unexpected_failed_responses
    assert not page_errors, page_errors
    browser.close()
