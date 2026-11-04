import os
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from backend.app.discovery.connectors import OpenStreetMapOverpassConnector

connector = OpenStreetMapOverpassConnector()
print("Overpass configured:", connector.is_configured())
actual_endpoint, redacted_endpoint = connector._resolve_endpoint()
print("Endpoint:", actual_endpoint)

test_scenarios = [
    {"city": "Bengaluru", "country": "India", "industry": "Restaurants", "limit": 3},
    {"city": "Bengaluru", "country": "India", "industry": "Clinics", "limit": 3},
    {"city": "Mumbai", "country": "India", "industry": "Restaurants", "limit": 3},
    {"city": "Gurugram", "country": "India", "industry": "IT services", "limit": 3},
    {"city": "Gurugram", "country": "India", "industry": "Real estate", "limit": 3},
]

for sc in test_scenarios:
    print(f"\n--- Testing Overpass: {sc['industry']} in {sc['city']} ---")
    start = time.time()
    try:
        leads = connector.search(
            query=sc['industry'],
            city=sc['city'],
            country=sc['country'],
            industry=sc['industry'],
            limit=sc['limit']
        )
        duration = time.time() - start
        last_err = getattr(connector, 'last_error', None)
        print(f"Status: {'Error: ' + last_err if last_err else 'Success'}, Time: {duration:.2f}s, Results: {len(leads)}")
        for i, lead in enumerate(leads):
            print(f"  [{i+1}] {lead.name} | Domain: {lead.domain or 'None (SQL NULL)'} | City: {lead.city} | Source: {lead.source_url}")
            if lead.phone: print(f"      Phone: {lead.phone}")
            if lead.email: print(f"      Email: {lead.email}")
    except Exception as e:
        duration = time.time() - start
        print(f"Exception after {duration:.2f}s: {e}")
