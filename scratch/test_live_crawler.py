import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from backend.app.discovery.connectors import WebsiteCrawlerConnector
from backend.app.research.qualification_engine import QualificationEngine

crawler = WebsiteCrawlerConnector()
print("WebsiteCrawler configured:", crawler.is_configured())

test_sites = [
    # IT Services (Bengaluru)
    {"url": "https://hasura.io", "name": "Hasura India", "city": "Bengaluru", "industry": "IT services"},
    # Healthcare / Clinics (Bengaluru)
    {"url": "https://practo.com", "name": "Practo Technologies", "city": "Bengaluru", "industry": "Clinics"},
    # Restaurants / Food (Mumbai)
    {"url": "https://box8.in", "name": "Box8", "city": "Mumbai", "industry": "Restaurants"},
    # Real Estate (Gurugram)
    {"url": "https://magicbricks.com", "name": "MagicBricks", "city": "Gurugram", "industry": "Real estate"}
]

for t in test_sites:
    print(f"\n=======================================================")
    print(f"CRAWLING LIVE: {t['url']} ({t['industry']} - {t['city']})")
    start = time.time()
    leads = crawler.search(query=t['url'], city=t['city'], country="India", industry=t['industry'], limit=1)
    duration = time.time() - start
    print(f"Duration: {duration:.2f}s | Leads discovered: {len(leads)}")
    if leads:
        lead = leads[0]
        print(f"Business Name: {lead.name}")
        print(f"Domain: {lead.domain}")
        print(f"Location: {lead.city}, {lead.country}")
        print(f"Phone: {lead.phone or 'Not published on homepage'}")
        print(f"Email: {lead.email or 'Not published on homepage'}")
        print(f"Source URL: {lead.source_url}")
        print(f"Confidence: {lead.evidence_confidence}")
        qual = lead.raw_metadata.get('qual_data', {})
        print(f"Business Quality: {qual.get('business_quality')}/100")
        print(f"Conversion Potential: {qual.get('conversion_potential')}/100")
        print("Service Opportunity Scores:")
        for opp in qual.get('opportunities', []):
            print(f"  - {opp['service']}: {opp['score']}/100 (Confidence: {opp['confidence']}) -> {opp['reason']}")
        contacts = lead.raw_metadata.get('contacts', [])
        print(f"Contacts extracted: {len(contacts)}")
        for c in contacts:
            print(f"  * {c.get('full_name')} ({c.get('job_title')}): email='{c.get('email')}', phone='{c.get('phone')}' via {c.get('contact_source')}")

