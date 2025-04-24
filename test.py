import os
import time
from playwright.sync_api import sync_playwright, Page, ElementHandle
from dotenv import load_dotenv
from google import genai

# Load Gemini API key
load_dotenv()
GEMINI_KEY = os.getenv("gemini_key")
client = genai.Client(api_key=GEMINI_KEY)

# Global history of actions
history = []

# Track consecutive identical actions to avoid loops
action_counts = {}

# Maximum history entries to include in prompt
MAX_HISTORY = 5


def detect_search_bar(page: Page) -> str:
    """
    Heuristic to find the most likely search input field on the page.
    Returns a CSS selector or empty string.
    """
    candidates = page.query_selector_all("input:visible")
    best = None
    best_score = 0
    for inp in candidates:
        score = 0
        try:
            for attr in ('placeholder', 'aria-label', 'name', 'id', 'type'):
                val = inp.get_attribute(attr) or ''
                if any(keyword in val.lower() for keyword in ['search', 'query', 'find']):
                    score += 1
        except:
            continue
        if score > best_score:
            best_score = score
            best = inp
    if best and best_score > 0:
        # generate a simple selector
        selector = best.evaluate(
            "el => el.id ? `#${el.id}` : el.getAttribute('name') ? `${el.tagName.toLowerCase()}[name=\"${el.getAttribute('name')}\"]` : el.tagName.toLowerCase()")
        return selector
    return ""


def detect_search_button(page: Page) -> str:
    """
    Heuristic to find a button that likely submits a search.
    Returns a CSS selector or empty string.
    """
    buttons = page.query_selector_all("button:visible")
    for btn in buttons:
        try:
            text = (btn.inner_text() or '').lower()
            attrs = ' '.join(filter(None, [btn.get_attribute(
                'aria-label'), btn.get_attribute('name'), btn.get_attribute('id')])).lower()
            if any(keyword in text for keyword in ['search', 'go', 'find', 'ask', '🔍']) or any(keyword in attrs for keyword in ['search', 'go', 'find', 'ask']):
                # generate a simple selector
                selector = btn.evaluate(
                    "el => el.id ? `#${el.id}` : el.tagName.toLowerCase() + (el.getAttribute('class') ? '.' + el.getAttribute('class').split(' ').join('.') : '')")
                return selector
        except:
            continue
    # fallback: input[type=submit]
    submits = page.query_selector_all("input[type=submit]:visible")
    if submits:
        inp = submits[0]
        return inp.evaluate("el => el.getAttribute('name') ? `${el.tagName.toLowerCase()}[name=\"${el.getAttribute('name')}\"]` : el.tagName.toLowerCase()")
    return ""


def search_tool(page: Page, query: str) -> bool:
    """
    Unified search: finds a search bar, fills it, and clicks the search button.
    Returns True if action performed.
    """
    sel_input = detect_search_bar(page)
    if not sel_input:
        return False
    try:
        page.fill(sel_input, query)
    except:
        return False
    time.sleep(1)
    sel_btn = detect_search_button(page)
    if sel_btn:
        try:
            page.click(sel_btn)
        except:
            pass
    return True


def ask_llm(page_text: str, inputs_snippet: str) -> str:

    mem = "None" if not history else "\n".join(history[-MAX_HISTORY:])

    prompt = f"""
You are a smart web browsing agent. You can browse and interact with websites using actions like 'click', 'fill', 'goto' or 'stop'.
Don't repeat actions you've already taken. Use memory to decide the next step based on prior interactions.
Try to not simply 'stop' in the first time itself (that is when the memory provided below is empty). 

Available actions:
- search(<query>): finds a search bar, enters the text, and submits.
- click(<selector>): click an element.
- fill(<selector>, <value>): fill an input field.
- goto(<url>): navigate to URL.
- stop(): end the session.

--- PAST ACTIONS (MEMORY) ---
{mem}

--- PAGE INPUT HINTS ---
{inputs_snippet or 'None'}

--- PAGE CONTENT (truncated) ---
{page_text[:3000]}

Decide the next action. Consider tasks that would normally (and logically) be done by a human, such as searching for something when you see a search bar, clicking on buttons to navigate and perform tasks, etc.
If you see HTML that indicates a search bar or input field (such as classes/elements containing the words search, input, query, form etc. They are also inside divs or form elements sometimes so look for it properly) then think of a random topic that you can search for return that topic in the "VALUE" field specified below.
If you have returned a VALUE to be filled in the last action that you took, look for a button that should be clicked to actually enter that input and go to the next page - and then return that target button along with a "click" action, as specified in the output format below. Specifically look for <button> elements with names/placeholders/aria labels as "Search", "Ask" or other related words in such cases.
If you see a "Accept Cookies" button click on it and then proceed further.
Do not repeat an action more than twice; if stuck, try a different strategy. 

Respond exactly in the following format:

ACTION: <click/fill/goto/stop>
TARGET: <CSS selector or URL>
VALUE: <Text to type if filling (such as search bars or other inputs), else leave empty>
"""
    res = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return res.text.strip()


def parse_response(response: str):
    """
    Parse LLM response into action, target, value.
    """
    lines = response.strip().splitlines()
    action = target = value = ""
    for line in lines:
        if line.startswith("ACTION:"):
            action = line.split(":", 1)[1].strip().lower()
        elif line.startswith("TARGET:"):
            target = line.split(":", 1)[1].strip()
        elif line.startswith("VALUE:"):
            value = line.split(":", 1)[1].strip()

    # update history and counts
    hist_entry = f"{action.upper()}: {target or value}"
    history.append(hist_entry)
    action_counts[action] = action_counts.get(action, 0) + 1

    return action, target, value


def run_agent(start_url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(start_url)
        time.sleep(3)

        # initial input hints
        inputs = page.query_selector_all("input")
        inputs_snippet = []
        for inp in inputs:
            try:
                label = inp.get_attribute("placeholder") or inp.get_attribute(
                    "aria-label") or inp.get_attribute("name") or inp.get_attribute("id") or ""
                snippet = inp.evaluate("el => el.outerHTML")
                inputs_snippet.append(
                    f"<input: {label}> snippet: {snippet[:120]}")
            except:
                continue
        inputs_snippet = "\n".join(inputs_snippet)

        while True:
            print("\n🧠 Reading page content...")
            page_text = page.content()

            response = ask_llm(page_text, inputs_snippet)
            print(f"🤖 LLM says: {response}")

            action, target, value = parse_response(response)

            # avoid infinite loops
            if action_counts.get(action, 0) > 3:
                print(f"⚠️ Action '{action}' repeated too often. Stopping.")
                break

            if action == "stop":
                print("✅ Agent stopped.")
                break

            performed = False
            try:
                if action == "search":
                    performed = search_tool(page, value)
                elif action == "click":
                    page.click(target, timeout=5000)
                    performed = True
                elif action == "fill":
                    page.fill(target, value)
                    performed = True
                elif action == "goto":
                    page.goto(target)
                    performed = True
                else:
                    print(f"⚠️ Unknown action: {action}")
            except Exception as e:
                print(f"❌ Failed to perform {action}: {e}")

            if not performed:
                print(
                    f"⚠️ Could not perform '{action}'. Trying alternative search if applicable.")
                if action != 'search' and 'search' in page.url:
                    # fallback to a generic search
                    search_tool(page, 'test')

            time.sleep(3)

        browser.close()


if __name__ == "__main__":
    run_agent("https://stackoverflow.com")
