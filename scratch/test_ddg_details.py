import httpx
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

r = httpx.post(
    "https://html.duckduckgo.com/html/",
    data={"q": "IT services companies in Bengaluru official website"},
    headers=headers,
    timeout=8.0
)
soup = BeautifulSoup(r.text, 'html.parser')
results = soup.find_all('div', class_='result')
print(f"Results found: {len(results)}")
for res in results[:8]:
    title_el = res.find('a', class_='result__snippet') or res.find('a', class_='result__title') or res.find('h2')
    snippet_el = res.find('a', class_='result__snippet')
    url_el = res.find('a', class_='result__url')
    if url_el:
        raw_href = url_el.get('href', '')
        # Unquote DDG redirect
        if 'uddg=' in raw_href:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
            target_url = p.get('uddg', [''])[0]
        else:
            target_url = raw_href
        print(" * Title:", res.find('a', class_='result__url').get_text(strip=True))
        print("   URL:", target_url)
        if snippet_el:
            print("   Snippet:", snippet_el.get_text(strip=True)[:100])

