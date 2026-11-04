import httpx

ql = """[out:json][timeout:25];
node["amenity"="restaurant"](12.971,77.592,12.979,77.605);
out 5;
"""
headers = {
    'User-Agent': 'SparkXFlowLeadEngine/1.0 (LeadDiscoveryEngine; contact@sparkxflow.local)'
}

for endpoint in [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter'
]:
    print(f"Testing {endpoint}...")
    try:
        r = httpx.post(endpoint, data={'data': ql}, headers=headers, timeout=25.0)
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        if r.status_code == 200:
            data = r.json()
            elems = data.get('elements', [])
            print(f"Success! Received {len(elems)} elements:")
            for el in elems[:5]:
                tags = el.get('tags', {})
                print(" -", tags.get('name'), "|", tags.get('amenity'), "|", tags.get('addr:street'))
            break
    except Exception as e:
        print("Error:", type(e).__name__, e)

