import httpx
from bs4 import BeautifulSoup
import urllib.parse
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def search_ddg_businesses(query, city, industry):
    search_term = f"{industry} {query} in {city} India official website"
    r = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": search_term},
        headers=headers,
        timeout=10.0
    )
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, 'html.parser')
    results = []
    directory_domains = {'tripadvisor', 'zomato', 'justdial', 'yellowpages', 'facebook', 'linkedin', 'instagram', 'twitter', 'wikipedia', 'quora', 'youtube'}
    
    for res in soup.find_all('div', class_='result'):
        url_el = res.find('a', class_='result__url')
        title_el = res.find('a', class_='result__title') or res.find('h2')
        snippet_el = res.find('a', class_='result__snippet')
        if not url_el or not title_el:
            continue
        
        raw_href = url_el.get('href', '')
        if 'uddg=' in raw_href:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
            target_url = p.get('uddg', [''])[0]
        else:
            target_url = raw_href
            
        parsed_target = urllib.parse.urlparse(target_url)
        domain = parsed_target.netloc.lower().replace('www.', '')
        if not domain or any(d in domain for d in directory_domains):
            continue
            
        raw_title = title_el.get_text(' ', strip=True)
        # Clean title to extract business name
        # Often title is "Acme Tech: Software Solutions..." or "Acme Tech - Bengaluru"
        clean_name = re.split(r'[:|\-–—]', raw_title)[0].strip()
        snippet = snippet_el.get_text(' ', strip=True) if snippet_el else ""
        
        results.append({
            'name': clean_name,
            'website': f"{parsed_target.scheme}://{parsed_target.netloc}",
            'domain': domain,
            'source_url': target_url,
            'snippet': snippet,
            'city': city
        })
    return results

for city in ["Bengaluru", "Mumbai", "Gurugram"]:
    for cat in ["Clinics", "IT services"]:
        found = search_ddg_businesses(cat, city, cat)
        print(f"\n{cat} in {city}: Found {len(found)} independent businesses:")
        for f in found[:3]:
            print(f" * {f['name']} | Domain: {f['domain']} | Web: {f['website']}")

