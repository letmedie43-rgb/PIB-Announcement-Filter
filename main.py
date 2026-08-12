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
        return list(set(articles))[:25] # সেরা ২৫টি হেডলাইন
    except Exception as e:
        print("Error fetching PIB:", e)
        return []

def summarize_with_claude(headlines):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"""
    নিচে PIB-এর আজকের ২৫টি খবরের তালিকা দেওয়া হলো:
    {chr(10).join(headlines)}

    তোমার কাজ:
    ১. এখান থেকে কেবল অর্থনীতি, কৃষি, বিজ্ঞান-প্রযুক্তি, সরকারি নীতি বা পরীক্ষা সংক্রান্ত ৩-৪টি সবচেয়ে গুরুত্বপূর্ণ খবর বেছে নাও।
    ২. প্রতিটি সংবাদের সারসংক্ষেপ বাংলা ভাষায় ২-৩টি পয়েন্টে লেখো।
    ৩. শেষে মূল সংবাদের লিংকটি যুক্ত করে দাও।
    ৪. অতিরিক্ত কোনো ভূমিকা বা উপসংহার লেখার দরকার নেই।
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
        "text": f"🗞️ **আজকের PIB বুলেটিন:**\n\n{text}",
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
