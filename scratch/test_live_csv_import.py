import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.app.models import Business, BusinessProfile, BusinessDomain
from backend.app.discovery.connectors import CsvSourceConnector
from backend.app.discovery.search_service import SearchService

db_url = os.environ.get('DATABASE_URL', 'sqlite:///./sparkxflow.db')
engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)

csv_data = """name,website,industry,city,country,phone,email,address
Dr. Agarwal's Eye Hospital,https://www.dragarwal.com,Clinics,Bengaluru,India,08048193411,info@dragarwal.com,"Koramangala, Bengaluru, Karnataka"
Hasura Technologies Pvt Ltd,https://hasura.io,IT services companies,Bengaluru,India,,,Bengaluru Karnataka
Box8 Hospitality Services,https://box8.in,Restaurants,Mumbai,India,,,Mumbai Maharashtra
DLF Real Estate Hub,https://www.dlf.in,Real estate agencies,Gurugram,India,+91-124-4334200,,"DLF Phase 2, Gurugram, Haryana"
Third Wave Coffee Roasters,,Restaurants,"Indiranagar, Bengaluru",India,,,"12th Main Road, Indiranagar, Bengaluru, Karnataka"
Third Wave Coffee Roasters,,Restaurants,"Koramangala, Bengaluru",India,,,"80 Feet Road, Koramangala, Bengaluru, Karnataka"
Hasura Technologies Private Limited,https://hasura.io,IT services companies,Bengaluru,India,,,Bengaluru Karnataka
"""

connector = CsvSourceConnector()
print("CSV Connector Configured:", connector.is_configured())

raw_leads = connector.parse_csv(csv_data)
print(f"Raw leads parsed from CSV: {len(raw_leads)}")

with SessionLocal() as session:
    initial_count = session.scalars(select(Business)).all()
    print(f"Pre-existing businesses in DB: {len(initial_count)}")
    
    service = SearchService(session)
    job = service.create_search_job(
        name="Phase 8 CSV Indian Validation Batch",
        query="Indian Business Leads",
        country="India",
        city="Bengaluru, Mumbai, Gurugram",
        industry="Multi-Sector",
        connector_name="csv_file",
        max_leads=50
    )
    
    # We pass the parsed leads directly into job execution logic
    # or simulate the exact connector search returning parsed leads
    from unittest.mock import patch
    with patch.object(CsvSourceConnector, 'search', return_value=raw_leads):
        res = service.execute_search_job(job.id)
    
    print("\nSearch Job Result:", res)
    
    # Verify records in DB
    all_biz = session.scalars(select(Business).order_by(Business.created_at.desc())).all()
    print(f"\nTotal businesses in DB now: {len(all_biz)}")
    print(f"Net new businesses added: {len(all_biz) - len(initial_count)}")
    
    for b in all_biz[:len(all_biz) - len(initial_count)]:
        prof = session.get(BusinessProfile, b.id)
        print(f" - [{b.id[:8]}] {b.name} | Domain: {b.domain or 'SQL NULL'} | Loc: {b.location} | Source: {b.source}")
        if prof and (prof.phone or prof.email):
            print(f"     Contacts: Phone={prof.phone or 'None'}, Email={prof.email or 'None'}")

