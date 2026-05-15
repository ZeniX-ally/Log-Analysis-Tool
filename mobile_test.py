from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 375, "height": 812},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
    page = context.new_page()
    page.goto("http://127.0.0.1:5000")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Screenshot dashboard
    page.screenshot(path="C:\\Log-Analysis-Tool\\dashboard_mobile.png", full_page=True)
    print("DASHBOARD screenshot saved")

    # Switch to failCenterPanel
    page.evaluate('mobileSwitchPanel("failCenterPanel", document.querySelector(".tab-item[data-panel=\\"failCenterPanel\\"]"))')
    page.wait_for_timeout(1500)
    page.screenshot(path="C:\\Log-Analysis-Tool\\fail_panel_mobile.png", full_page=True)
    print("FAIL panel screenshot saved")

    # Switch to limitPanel
    page.evaluate('mobileSwitchPanel("limitPanel", document.querySelector(".tab-item[data-panel=\\"limitPanel\\"]"))')
    page.wait_for_timeout(1500)
    page.screenshot(path="C:\\Log-Analysis-Tool\\limit_panel_mobile.png", full_page=True)
    print("LIMIT panel screenshot saved")

    browser.close()