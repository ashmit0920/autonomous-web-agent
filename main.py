from playwright.sync_api import sync_playwright


def get_search_query_from_ai():
    return "chatgpt"


def run_browser_agent():
    query = get_search_query_from_ai()
    print(f"🔍 AI wants to search: {query}")

    with sync_playwright() as p:
        # set to True to hide browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        # page.goto("https://www.google.com")
        page.goto("https://www.wikipedia.org")

        # Accept cookies if needed (common for EU regions)
        try:
            page.locator("button:has-text('Accept all')").click(timeout=2000)
        except:
            pass

        # Type the AI-provided query
        page.fill("input[name='search']", query)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        # Click the first result
        print(page.locator("p").first)
        page.wait_for_timeout(5000)

        print("✅ First result clicked. Task done.")

        # browser.close()


if __name__ == "__main__":
    run_browser_agent()
