import httpx
import json

# Query Wikidata for companies headquartered in Bengaluru or Mumbai
sparql_bengaluru = """
SELECT ?item ?itemLabel ?website ?coords WHERE {
  ?item wdt:P31/wdt:279* wd:Q4830453. # instance or subclass of business enterprise
  ?item wdt:P159 wd:Q1355. # headquarters in Bengaluru
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P625 ?coords. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} LIMIT 10
"""

url = "https://query.wikidata.org/sparql"
headers = {
    "User-Agent": "SparkXFlowLeadEngine/1.0 (AutonomousDiscoveryValidation; contact@sparkxflow.local)",
    "Accept": "application/json"
}

try:
    r = httpx.get(url, params={"query": sparql_bengaluru, "format": "json"}, headers=headers, timeout=10.0)
    print("Wikidata status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        bindings = data.get('results', {}).get('bindings', [])
        print(f"Wikidata returned {len(bindings)} companies in Bengaluru:")
        for b in bindings[:5]:
            name = b.get('itemLabel', {}).get('value')
            web = b.get('website', {}).get('value')
            print(f" * {name} | Website: {web}")
except Exception as e:
    print("Wikidata error:", e)

