import os
import requests
from bs4 import BeautifulSoup
import anthropic

# Fetch keys from GitHub Secrets
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_pib_headlines():
    url = "https://pib.gov.in/AllRelease.aspx"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        articles = []
        for a in soup.find_all("a", href=True):
            if "PRID=" in a["href"] or "PressReleaseDetail" in a["href"]:
                title = a.get_text(strip=True)
                link = a["href"] if a["href"].startswith("http") else "https://pib.gov.in/" + a["href"]
                if title and len(title) > 20:
                    articles.append(f"- {title} (URL: {link})")
        return list(set(articles))[:30] # Fetch top 30 headlines for wider analysis
    except Exception as e:
        print("Error fetching PIB:", e)
        return []

def summarize_with_claude(headlines):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"""
    You are an expert Indian Stock Market Equity Analyst. Analyze the following PIB announcements for their direct or indirect financial impact on the Indian Stock Market (NSE/BSE), specific sectors, or listed companies.

    PIB Announcements:
    {chr(10).join(headlines)}

    EVALUATION & FILTERING RULES:
    1. Assign a Stock Market Impact Score from 1 to 10 for each announcement based on its potential to move stock prices, sector indices, or corporate revenues (e.g., policy changes, subsidies, PLI schemes, export/import duties, defense orders, infrastructure spend).
    2. STRICT RULE: Completely DISREGARD and OMIT any announcement with an Impact Score of 1, 2, or 3, or anything irrelevant to the stock market. Do NOT include them in the output at all.
    3. ONLY process announcements with an Impact Score of 4 or higher (4 to 10).

    OUTPUT FORMAT FOR SELECTED ANNOUNCEMENTS (Score 4-10):

    📌 Title: [Title of Announcement]
    📊 Impact Score: [X/10]
    🏭 Affected Sectors & Stocks: [e.g., Defence (HAL, BEL), Sugar (Balrampur Chini), Renewable Energy, etc.]
    📈 Market Sentiment & Analysis:
    - [Bullish / Bearish / Neutral statement with brief reasoning]
    - [Key policy detail or catalyst driving the impact]
    🔗 Link: [Original URL]

    If NO announcement scores 4 or above, simply output: "No high-impact stock market announcements found today."
    Do NOT include any introductory or concluding text.
    """
    
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"📈 **PIB Stock Market Radar:**\n\n{text}",
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    headlines = get_pib_headlines()
    if headlines:
        summary = summarize_with_claude(headlines)
        send_telegram(summary)
    else:
        print("No headlines found.")
