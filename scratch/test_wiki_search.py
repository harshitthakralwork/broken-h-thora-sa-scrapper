import httpx
import json

url = "https://en.wikipedia.org/w/api.php"
params = {
    "action": "query",
    "list": "search",
    "srsearch": "companies in Bengaluru technology",
    "format": "json",
    "srlimit": 5
}
headers = {
    "User-Agent": "SparkXFlowLeadEngine/1.0 (Testing Research; contact@sparkxflow.local)"
}

try:
    r = httpx.get(url, params=params, headers=headers, timeout=5.0)
    print("Wikipedia status:", r.status_code)
    data = r.json()
    items = data.get("query", {}).get("search", [])
    print(f"Results: {len(items)}")
    for item in items:
        print(" *", item.get("title"))
except Exception as e:
    print("Error:", e)

