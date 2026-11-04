import httpx

ql = """[out:json][timeout:15];
node["amenity"="restaurant"](12.97,77.59,12.98,77.60);
out 3;
"""
try:
    r = httpx.post(
        'https://overpass-api.de/api/interpreter',
        data={'data': ql},
        headers={'User-Agent': 'SparkXFlowLeadEngine/1.0 (Testing Live Connectivity)'},
        timeout=20.0
    )
    print("Status:", r.status_code)
    print("Length:", len(r.text))
    print("Snippet:", r.text[:300])
except Exception as e:
    print("Error:", type(e).__name__, str(e))

