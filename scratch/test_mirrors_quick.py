import httpx
import json

mirrors = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter'
]

ql = """[out:json][timeout:10];
node["amenity"="restaurant"](12.97,77.59,12.98,77.61);
out 3;
"""

for m in mirrors:
    try:
        r = httpx.post(m, data={'data': ql}, headers={'User-Agent': 'SparkXFlowLeadEngine/1.0'}, timeout=10.0)
        print(f"{m} -> HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            elems = data.get('elements', [])
            print(f"   Received {len(elems)} elements:")
            for el in elems[:3]:
                tags = el.get('tags', {})
                print(f"    * {tags.get('name')} | amenity: {tags.get('amenity')} | website: {tags.get('website')}")
    except Exception as e:
        print(f"{m} -> {type(e).__name__}: {e}")

