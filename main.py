import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_KEY = os.getenv("gemini_key")

client = genai.Client(api_key=GEMINI_KEY)


def ask_llm(page_text):
    prompt = f"""
You are a web browsing agent. You see the following content on a webpage:

--- PAGE CONTENT START ---

{page_text[:4000]}

--- PAGE CONTENT END ---

What should you do next? Consider tasks that would normally (and logically) be done by a human, such as searching for something when you see a search bar, clicking on buttons to navigate and perform tasks, etc.
If you see HTML that indicates a search bar or input field (such as classes named search, input, query, etc.) then think of a random topic that you can search for return that topic in the "VALUE" field specified below.

Respond in this format:
ACTION: <click/fill/goto/stop>
TARGET: <CSS selector or URL>
VALUE: <Text to type if filling (such as search bars or other inputs), else leave empty>
"""

    res = client.models.generate_content(
        model="gemini-2.5-flash-preview-04-17",
        contents=prompt,
    )

    return res.text


def parse_response(response):
    lines = response.strip().splitlines()
    action = target = value = ""
    for line in lines:
        if line.startswith("ACTION:"):
            action = line.split(":", 1)[1].strip().lower()
        elif line.startswith("TARGET:"):
            target = line.split(":", 1)[1].strip()
        elif line.startswith("VALUE:"):
            value = line.split(":", 1)[1].strip()
    return action, target, value


def run_agent(start_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(start_url)

        while True:
            print("\n🧠 Reading page content...")
            page_text = page.content()

            response = ask_llm(page_text)
            print(f"🤖 LLM says: \n{response}")

            action, target, value = parse_response(response)

            if action == "stop":
                print("✅ Agent stopped.")
                break

            try:
                if action == "click":
                    page.click(target, timeout=5000)
                elif action == "fill":
                    page.fill(target, value)
                elif action == "goto":
                    page.goto(target)
                else:
                    print(f"⚠️ Unknown action: {action}")
            except Exception as e:
                print(f"❌ Failed to perform action: {e}")

            time.sleep(3)  # wait before the next step

        browser.close()


if __name__ == "__main__":
    run_agent("https://www.wikipedia.org")
