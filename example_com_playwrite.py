from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")

    title = page.title()
    print(f"Page title: {title}")

    # Click the "More information..." link
    page.click("a:has-text('Learn More')")

    # Wait for navigation to complete
    page.wait_for_load_state("networkidle")

    print(f"\nNavigated to: {page.url}")
    print(f"New page title: {page.title()}")
    print("\n--- Page Content ---")
    print(page.inner_text("body"))

    browser.close()
