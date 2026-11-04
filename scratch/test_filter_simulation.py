import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv('.env')
token = os.environ.get('ADMIN_TOKEN')
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/leads',
    headers={'Authorization': f'Bearer {token}'}
)
leads = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
print('Total leads:', len(leads))

queries = ['Bengaluru', 'Mumbai', 'Gurugram', 'Restaurants', 'Clinics', 'Real estate', 'IT services']
for q in queries:
    matched = [
        l['name'] for l in leads
        if any(q.lower() in (l.get(k) or '').lower() for k in ('name', 'domain', 'industry', 'location'))
    ]
    print(f"Filter '{q}': {len(matched)} match(es) -> {matched}")

