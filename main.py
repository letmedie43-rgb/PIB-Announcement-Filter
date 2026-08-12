import os
import requests
from bs4 import BeautifulSoup
import anthropic

# Fetch secrets from GitHub
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

EXCLUDE_KEYWORDS = [
    "greetings", "wishes", "birth anniversary", "death anniversary", "condoles", 
    "tribute", "homage", "jayanti", "sports", "swachhata", "inaugurates exhibition", 
    "book release", "felicitates", "moharram", "diwali", "eid", "pujas", "appointment",
    "prizes", "awards", "medal", "tournament", "courtesy call", "cultural", "exhibition"
]

def get_filtered_pib_releases():
    url = "https://pib.gov.in/AllRelease.aspx"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    releases = []
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        for a in soup.find_all("a", href=True):
            if "PRID=" in a["href"] or "PressReleaseDetail" in a["href"]:
                title = a.get_text(strip=True)
                link = a["href"] if a["href"].startswith("http") else "https://pib.gov.in/" + a["href"]
                
                if title and len(title) > 20:
                    title_lower = title.lower()
                    if not any(keyword in title_lower for keyword in EXCLUDE_KEYWORDS):
                        releases.append({"title": title, "url": link})
        
        # Deduplicate
        seen = set()
        unique_releases = []
        for r in releases:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique_releases.append(r)
                
        # Limit to top 15 filtered releases to avoid hanging/rate limits
        return unique_releases[:15]
    except Exception as e:
        print("Error fetching release list:", e)
        return []

def extract_article_body(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        # Strict 5 second timeout to prevent hanging
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
    
    combined_content = ""
    for idx, rel in enumerate(releases, 1):
        body = extract_article_body(rel["url"])
        if body:
            combined_content += f"\n[ARTICLE {idx}]\nTitle: {rel['title']}\nBody:\n{body}\n"

    if not combined_content:
        return "No relevant market articles found."

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
📌 Title: [Title]
📊 Score: [X/10]
🏭 Sectors & Stocks: [Sectors and potential stock tickers]
📈 Sentiment & Catalyst: [Bullish/Bearish] - [1 short sentence trigger]

If no article scores 4+, output: "No high-impact announcements found today."
No introductory or concluding text.
"""

    response = client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"📈 **Stock Market Radar**\n\n{text}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    releases = get_filtered_pib_releases()
    if releases:
        summary = analyze_with_claude(releases)
        send_telegram(summary)
    else:
        print("No releases found today.")
