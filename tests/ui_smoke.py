import os

from playwright.sync_api import sync_playwright


URL = os.environ.get("XIAOXUE_TEST_URL", "http://127.0.0.1:5173/")


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
    assert tabs == ['队伍资料', '当前赛事', '足球', 'TK资料库', '项目中心'], tabs
    assert page.get_by_role("button", name="当前赛事", exact=True).get_attribute("class").find("active") >= 0
    page.wait_for_function(
        "() => document.querySelector('#event-match-list').innerText.length > 0",
        timeout=10_000,
    )
    event = visible_text(page)
    assert page.locator("#event-match-list .event-match-button").count() >= 0
    assert "近期比赛" in event
    if page.locator("#event-match-list .event-match-button").count():
        page.locator("#event-match-list .event-match-button").first.click()
        page.wait_for_function(
            "() => document.querySelector('#event-match-desk .match-desk-title h2')?.innerText.includes('vs')",
            timeout=10_000,
        )
        assert "已选比赛" in page.locator("#event-match-desk").inner_text()
        assert "综合实力" in page.locator("#event-match-desk").inner_text()
    page.screenshot(path="/tmp/xiaoxue-event.png", full_page=True)

    page.get_by_role("button", name="队伍资料", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('#fundamentals-table').innerText.length > 0",
        timeout=10_000,
    )
    assert page.locator("#fundamentals-table .fund-row").count() > 0
    assert page.locator("#col-profile").is_hidden()
    page.screenshot(path="/tmp/xiaoxue-teams-overview.png", full_page=True)
    page.locator("#fundamentals-table .fund-row[data-team]").first.click()
    page.wait_for_timeout(300)
    assert page.locator("#col-profile").is_visible()

    page.get_by_role("button", name="TK资料库", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('#tk-library-results').innerText.includes('读取中')",
        timeout=10_000,
    )
    assert page.locator("#card-tk-library").is_visible()
    page.select_option("#tk-library-team", "")
    page.locator('[data-tk-action="apply-filters"]').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#tk-library-results .tk-library-card').length > 0",
        timeout=10_000,
    )
    assert page.locator("#tk-library-results .tk-library-card").count() > 0
    page.screenshot(path="/tmp/xiaoxue-tk-library.png", full_page=True)
    page.locator("#tk-library-results .tk-library-note").first.click()
    page.wait_for_function(
        "() => document.querySelector('#tk-reader-content').innerText.length > 100",
        timeout=10_000,
    )
    assert page.locator("#card-tk-library.tk-reader-open").is_visible()
    page.screenshot(path="/tmp/xiaoxue-tk-reader.png", full_page=True)

    page.get_by_role("button", name="项目中心", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('#project-center')?.innerText.includes('交易人生项目')",
        timeout=10_000,
    )
    assert page.locator("#project-center").is_visible()
    assert page.get_by_text("项目负责什么", exact=True).is_visible()
    assert page.get_by_text("小雪负责什么", exact=True).count() == 0
    page.screenshot(path="/tmp/xiaoxue-project-center.png", full_page=True)
    assert not failed_responses, failed_responses
    assert not page_errors, page_errors
    browser.close()
