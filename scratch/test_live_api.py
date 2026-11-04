import os
import json
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path('.env'))
token = os.environ.get('ADMIN_TOKEN')
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/discovery/connectors',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print(f"Total live connectors: {len(data)}")
    for item in data:
        print(f" - {item['name']}: {item['title']} [{item['status']}]")
        print(f"   Attribution: {item.get('attribution')}")
        print(f"   Regions: {item.get('supported_regions')}")

# Test querying /api/discovery/jobs
req_jobs = urllib.request.Request(
    'http://127.0.0.1:8000/api/discovery/jobs',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(req_jobs) as resp:
    jobs = json.loads(resp.read().decode('utf-8'))
    print(f"\nRecent discovery jobs in DB: {len(jobs)}")

