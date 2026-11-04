import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from backend.app.discovery.connectors import WebsiteCrawlerConnector

crawler = WebsiteCrawlerConnector()
candidates = [
    {"url": "https://zerodha.com", "city": "Bengaluru", "ind": "Financial Services"},
    {"url": "https://mokobara.com", "city": "Bengaluru", "ind": "E-commerce & Retail"},
    {"url": "https://postman.com", "city": "Bengaluru", "ind": "IT services"}
]

for c in candidates:
    print(f"\nCrawling {c['url']}...")
    leads = crawler.search(query=c['url'], city=c['city'], country="India", industry=c['ind'], limit=1)
    if leads:
        lead = leads[0]
        print(f"Name: {lead.name}")
        print(f"Domain: {lead.domain}")
        print(f"Phone: {lead.phone}")
        print(f"Email: {lead.email}")
        contacts = lead.raw_metadata.get('contacts', [])
        print(f"Contacts found ({len(contacts)}):")
        for ct in contacts:
            print(" -", ct)
    else:
        print("No leads or blocked by robots/anti-bot")

