from playwright.sync_api import sync_playwright
import time

input_info = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://stackoverflow.com/questions")

    time.sleep(3)

    search_inputs = page.query_selector_all("input")
    for inp in search_inputs:
        try:
            tag_text = inp.get_attribute("placeholder") or inp.get_attribute(
                "aria-label") or inp.get_attribute("name") or inp.get_attribute("id")
            outer_html = inp.evaluate("el => el.outerHTML")
            print(f"<input: {tag_text}> html snippet: {outer_html[:150]}")
        except Exception as e:
            print("⚠️ Error reading input:", e)
