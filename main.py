import os
import re
import sys
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import anthropic

IST = timezone(timedelta(hours=5, minutes=30))

# Fetch secrets from GitHub Secrets
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Fail fast with a clear message instead of a confusing 401 deep in the SDK
missing = [name for name, val in [
    ("ANTHROPIC_API_KEY", ANTHROPIC_KEY),
    ("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
] if not val]
if missing:
    print(f"Missing required environment variables: {missing}. "
          f"Check that these are set as GitHub Secrets and that this workflow "
          f"has access to them (repo secrets vs. environment-scoped secrets).")
    sys.exit(1)

# Current active model (Aug 2026). claude-sonnet-5 gives better judgment on
# impact scoring than Haiku for roughly the same price right now.
MODEL_NAME = "claude-sonnet-5"
# Cheaper fallback if you want to cut cost further: "claude-haiku-4-5-20251001"

EXCLUDE_KEYWORDS = [
    "greetings", "wishes", "birth anniversary", "death anniversary", "condoles",
    "tribute", "homage", "jayanti", "sports", "swachhata", "inaugurates exhibition",
    "book release", "felicitates", "moharram", "diwali", "eid", "pujas", "appointment",
    "prizes", "awards", "medal", "tournament", "courtesy call", "cultural", "exhibition"
]

def get_filtered_pib_releases():
    # reg=48 = all ministries, all regions; lang=1 = English.
    # This page groups releases BY MINISTRY, not chronologically, so we
    # must filter by the "Posted on:" date rather than take the first N
    # <a> tags -- otherwise ministries listed later (Railway, Finance,
    # Commerce, Coal, etc.) never get a chance to appear.
    url = "https://www.pib.gov.in/allRel.aspx?reg=48&lang=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    releases = []

    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%d %b %Y")
    yesterday_str = (now_ist - timedelta(days=1)).strftime("%d %b %Y")
    all_seen_dates = set()  # for self-diagnosis

    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")

        for a in soup.find_all("a", href=True):
            if "PRID=" not in a["href"]:
                continue

            title = a.get_text(strip=True)
            if not title or len(title) <= 20:
                continue

            title_lower = title.lower()
            if any(keyword in title_lower for keyword in EXCLUDE_KEYWORDS):
                continue

            # "Posted on: DD Mon YYYY" appears as the next text node right
            # after the <a> tag in the page. find_next() walks the parse
            # tree directly instead of guessing the enclosing tag name.
            posted_date = None
            next_text = a.find_next(string=re.compile(r"Posted on:"))
            if next_text:
                m = re.search(r"Posted on:\s*(\d{1,2}\s\w{3}\s\d{4})", next_text)
                if m:
                    posted_date = m.group(1)

            all_seen_dates.add(posted_date)
            releases.append({"title": title, "url": None, "posted_date": posted_date, "href": a["href"]})

        seen = set()
        unique_releases = []
        for r in releases:
            if r["href"] not in seen:
                seen.add(r["href"])
                unique_releases.append(r)

        # Prefer strictly today's releases. Only fall back to yesterday's
        # date if today has zero matches -- this covers runs that land
        # right around midnight IST (queue delays, late manual test runs)
        # without double-reporting yesterday's news on a normal run.
        todays = [r for r in unique_releases if r["posted_date"] == today_str]
        chosen = todays
        used_date = today_str
        if not chosen:
            chosen = [r for r in unique_releases if r["posted_date"] == yesterday_str]
            used_date = yesterday_str

        for r in chosen:
            r["url"] = r["href"] if r["href"].startswith("http") else "https://www.pib.gov.in" + r["href"]

        print(f"Found {len(chosen)} releases posted on {used_date} after filtering "
              f"(today={today_str} had {len(todays)} matches).")
        if len(chosen) == 0:
            print(f"DEBUG - no matches. Sample of dates actually parsed from the page: {list(all_seen_dates)[:8]}")
        return chosen
    except Exception as e:
        print("Error fetching release list:", e)
        return []

def extract_article_body(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.content, "html.parser")
        paragraphs = soup.find_all("p")
        text_list = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 25]
        full_text = "\n".join(text_list)
        if not full_text:
            full_text = soup.get_text(strip=True)
        return full_text[:1200]
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""

def analyze_with_claude(releases):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Cap how many articles we send in one go to control input token cost
    # on busier news days -- date filtering already keeps this to "today
    # only", but a heavy day can still have 40-70 releases across ministries.
    releases = releases[:40]

    combined_content = ""
    for idx, rel in enumerate(releases, 1):
        body = extract_article_body(rel["url"])
        if body:
            combined_content += f"\n[ARTICLE {idx}]\nTitle: {rel['title']}\nBody:\n{body}\n"

    if not combined_content:
        return "No relevant market articles found today."

    prompt = f"""
You are an Indian stock market equity analyst. Evaluate the following PIB press releases for direct market/sector impact.

Content:
{combined_content}

RULES:
1. Assign an Impact Score from 1 to 10 based on market-moving potential.
2. STRICT FILTER: Completely OMIT scores 1, 2, and 3. Output nothing for them.
3. Process ONLY items scoring 4 to 10.
4. Output MUST be extremely concise. Do NOT include URLs or policy details.

OUTPUT FORMAT (Score 4-10 only):
Title: [Title]
Score: [X/10]
Sectors & Stocks: [Sectors and potential stock tickers]
Sentiment & Catalyst: [Bullish/Bearish] - [1 short sentence trigger]

If no article scores 4+, output: "No high-impact announcements found today."
No introductory or concluding text.
"""

    try:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=1200,  # raised from 500 -- more releases can now qualify
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except anthropic.AuthenticationError as e:
        print(f"AUTH ERROR - check ANTHROPIC_API_KEY secret (value/scope/whitespace): {e}")
        raise
    except anthropic.NotFoundError as e:
        print(f"MODEL NOT FOUND - '{MODEL_NAME}' may have been retired. "
              f"Check https://platform.claude.com/docs/en/about-claude/model-deprecations : {e}")
        raise
    except anthropic.APIStatusError as e:
        print(f"API ERROR {e.status_code}: {e.message}")
        raise

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"📈 Stock Market Radar\n\n{text}"
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        print("Telegram API Error:", res.text)
    else:
        print("Telegram message sent successfully.")

if __name__ == "__main__":
    releases = get_filtered_pib_releases()
    if releases:
        summary = analyze_with_claude(releases)
        send_telegram(summary)
    else:
        print("No releases found today.")
