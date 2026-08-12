import os
import requests
from bs4 import BeautifulSoup
import anthropic

# Secrets থেকে মান সংগ্রহ
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
        return list(set(articles))[:25] # Top 25 headlines
    except Exception as e:
        print("Error fetching PIB:", e)
        return []

def summarize_with_claude(headlines):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"""
    Here is a list of today's top 25 PIB announcements:
    {chr(10).join(headlines)}

    Task:
    1. Select 3-4 most important announcements related to Economy, Agriculture, Science & Technology, Government Policies, or Key Updates.
    2. Provide a concise summary for each selected announcement in English using 2-3 short bullet points.
    3. Include the original release URL at the end of each summary.
    4. Do not include any introductory or concluding text.
    """
    
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🗞️ **Today's PIB Digest:**\n\n{text}",
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
