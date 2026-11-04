import os
import sys
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.app.models import Business, BusinessProfile, LeadQualification, Contact, ResearchHistory

db_url = os.environ.get('DATABASE_URL', 'sqlite:///./sparkxflow.db')
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)

with SessionLocal() as session:
    b = session.scalars(select(Business).where(Business.domain == 'dragarwal.com')).first()
    assert b is not None, "Business dragarwal.com not found"
    lead_id = b.id
    print(f"Testing live research for business: {b.name} ({lead_id}) - {b.website}")

token = os.environ.get('ADMIN_TOKEN')
req = urllib.request.Request(
    f"http://127.0.0.1:8000/api/leads/{lead_id}/research",
    headers={'Authorization': f'Bearer {token}'},
    data=b"",
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        res_data = json.loads(resp.read().decode('utf-8'))
        print("Research API HTTP Status:", resp.status)
        print("Business Researched At:", res_data.get('researched_at'))
except Exception as e:
    print("Research API Error:", e)

# Check database for qualification and contacts
with SessionLocal() as session:
    qual = session.scalars(select(LeadQualification).where(LeadQualification.business_id == lead_id)).first()
    if qual:
        print("\nLeadQualification in DB:")
        print(f"  Business Quality Score: {qual.business_quality_score}/100")
        print(f"  Conversion Potential: {qual.conversion_potential_score}/100")
        print(f"  Evidence Confidence: {qual.evidence_confidence}")
        opps = json.loads(qual.service_scores_json or '[]')
        print(f"  Total Service Opportunities Scored: {len(opps)}")
        for o in opps:
            print(f"    - {o['service']}: {o['score']}/100 ({o['confidence']}) -> {o['reason']}")
    else:
        print("No LeadQualification recorded.")

    contacts = session.scalars(select(Contact).where(Contact.business_id == lead_id)).all()
    print(f"\nContacts in DB for this business: {len(contacts)}")
    for c in contacts:
        print(f"  - {c.full_name} ({c.job_title}) | Email: {c.email or 'None'} | Phone: {c.phone or 'None'} | Source: {c.contact_source}")

