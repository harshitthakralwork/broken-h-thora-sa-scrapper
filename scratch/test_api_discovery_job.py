import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv('.env')
token = os.environ.get('ADMIN_TOKEN')

payload = {
    "name": "Live API Crawler Discovery Test",
    "query": "https://hasura.io",
    "country": "India",
    "city": "Bengaluru",
    "state": "Karnataka",
    "industry": "IT services",
    "category": "GraphQL & APIs",
    "target_service": "Website Development",
    "max_leads": 5,
    "connector_name": "website_crawler"
}

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/discovery/jobs',
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    },
    data=json.dumps(payload).encode('utf-8'),
    method='POST'
)

with urllib.request.urlopen(req, timeout=30) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    print("API Job Creation Response:")
    print(json.dumps(res, indent=2))

