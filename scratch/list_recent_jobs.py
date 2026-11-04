import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv('.env')
token = os.environ.get('ADMIN_TOKEN')
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/discovery/jobs',
    headers={'Authorization': f'Bearer {token}'}
)
jobs = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
print(f"Total jobs: {len(jobs)}")
for j in jobs[:6]:
    print(f" - {j['name']} [{j['status']}] results: {j['results_count']}, connector: {j['connector_name']}")
    if j.get('error_log'):
        print(f"   log: {j['error_log'][:120]}")

