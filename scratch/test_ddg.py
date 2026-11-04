import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 1. Test DDG HTML search
try:
    r = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": "restaurants in Bengaluru site:in OR site:com"},
        headers=headers,
        timeout=8.0
    )
    print("DDG HTML status:", r.status_code)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, 'html.parser')
    results = soup.find_all('a', class_='result__url')
    print(f"DDG results count: {len(results)}")
    for res in results[:5]:
        print(" *", res.get_text(strip=True), "->", res.get('href'))
except Exception as e:
    print("DDG HTML error:", e)

