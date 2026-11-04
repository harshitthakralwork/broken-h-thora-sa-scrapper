"""End-to-end test suite for Phase 9 — Autonomous Business Discovery Engine.
Verifies the complete autonomous pipeline:
1. User enters city, state, industry, and category.
2. Discovery returns candidate business with official website.
3. Autonomous engine automatically invokes compliant crawler.
4. Schema.org and public contacts are extracted and linked to Business.
5. Evidence-based 9-service qualification is analyzed and stored.
6. Provenance clearly marks autonomous discovery vs CSV import.
7. Absence of features does not imply buying intent.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    Base, Business, BusinessDomain, BusinessProfile, Contact,
    LeadQualification, ResearchHistory, SearchJob
)
from app.discovery.connectors import DiscoveredLead, BaseConnector
from app.discovery.search_service import SearchService


@pytest.fixture
def autonomous_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_autonomous_discovery_and_qualification_pipeline(autonomous_db):
    """Test full 4-stage autonomous discovery pipeline:
    Discover Entity -> Resolve Official Domain -> Crawl Website -> Extract Contacts & Qualify.
    """
    service = SearchService(autonomous_db)

    # 1. User configures autonomous job for Bengaluru, Karnataka, Logistics
    job = service.create_search_job(
        name="Autonomous Bengaluru Logistics",
        query="",
        country="India",
        city="Bengaluru, Karnataka",
        industry="Supply Chain & Logistics",
        category="Logistics",
        target_service="Website Development",
        is_autonomous=True,
        connector_name="osm_overpass",
        max_leads=5
    )

    discovered_lead = DiscoveredLead(
        name="VRL Logistics Limited",
        website="https://www.vrllogistics.com",
        domain="vrllogistics.com",
        country="India",
        city="Bengaluru",
        address="Bangalore, Karnataka, India",
        industry="Logistics",
        source_name="OpenStreetMap Overpass (ODbL)",
        source_url="https://www.openstreetmap.org/node/99887766",
        connector_name="osm_overpass"
    )

    crawled_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VRL Logistics Ltd - Official Corporate Portal</title>
        <meta name="description" content="India premier surface transportation and commercial parcel delivery network.">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Corporation",
            "name": "VRL Logistics Limited",
            "telephone": "+91-80-26753000",
            "email": "customercare@vrllogistics.com",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Bengaluru",
                "addressRegion": "Karnataka",
                "addressCountry": "India"
            }
        }
        </script>
    </head>
    <body>
        <h1>VRL Logistics Corporate Portal</h1>
        <form action="/track" method="GET">
            <input name="consignment_no" placeholder="Track Consignment"/>
            <button type="submit">Track</button>
        </form>
        <a href="mailto:investor@vrllogistics.com">Investor Relations</a>
        <a href="https://linkedin.com/company/vrllogistics">LinkedIn</a>
    </body>
    </html>
    """

    # Mock connector search to return the discovered lead
    mock_connector = MagicMock()
    mock_connector.name = "osm_overpass"
    mock_connector.is_configured.return_value = True
    mock_connector.search.return_value = [discovered_lead]

    with patch('app.discovery.search_service.get_connector', return_value=mock_connector), \
         patch('app.crawl_client.run_crawl', return_value=('https://www.vrllogistics.com', crawled_html)):

        result = service.execute_search_job(job.id)

        assert result['status'] == 'completed'
        assert result['added'] == 1

        # 2. Verify Business stored with clear autonomous provenance
        b = autonomous_db.scalars(select(Business).where(Business.domain == "vrllogistics.com")).first()
        assert b is not None
        assert b.name == "VRL Logistics Limited"
        assert "Autonomous Discovery" in b.source
        assert "OpenStreetMap" in b.source
        assert b.researched_at is not None

        # 3. Verify Contacts automatically extracted from Schema.org and mailto links
        contacts = autonomous_db.scalars(select(Contact).where(Contact.business_id == b.id)).all()
        assert len(contacts) >= 2
        emails = [c.email for c in contacts]
        assert "customercare@vrllogistics.com" in emails
        assert "investor@vrllogistics.com" in emails
        for c in contacts:
            assert c.verification_status in ('unverified_public', 'verified')
            assert "vrllogistics.com" in c.contact_source

        # 4. Verify Qualification automatically computed with distinct dimensions
        qual = autonomous_db.scalars(select(LeadQualification).where(LeadQualification.business_id == b.id)).first()
        assert qual is not None
        assert qual.business_quality_score >= 70
        assert qual.conversion_potential_score >= 40
        assert qual.evidence_confidence in ('high', 'medium')

        # 5. Check 9 services scored with explicit separation of observed state and buying intent
        service_scores = json.loads(qual.service_scores_json)
        assert len(service_scores) == 9
        for s in service_scores:
            assert 'service' in s
            assert 'score' in s
            assert 'observed_technical_state' in s
            assert s['buying_intent_status'] == 'unknown'


def test_provenance_distinguishes_csv_from_autonomous(autonomous_db):
    """CSV records must be explicitly marked as CSV imports while autonomous records are marked as discovered."""
    service = SearchService(autonomous_db)

    # Lead 1: from CSV
    lead_csv = DiscoveredLead(
        name="Alpha Exports Pvt Ltd",
        website="https://alphaexports.in",
        domain="alphaexports.in",
        country="India",
        city="Mumbai",
        source_name="User CSV Dataset",
        source_url="leads_upload.csv",
        connector_name="csv_file"
    )

    # Lead 2: from autonomous connector
    lead_auto = DiscoveredLead(
        name="Beta Medical Clinic",
        website="https://betaclinic.in",
        domain="betaclinic.in",
        country="India",
        city="Gurugram",
        source_name="OpenStreetMap Overpass (ODbL)",
        source_url="https://www.openstreetmap.org/node/12345",
        connector_name="osm_overpass"
    )

    job = service.create_search_job(name="Provenance Test", connector_name="mock_connector", is_autonomous=False)

    mock_conn = MagicMock()
    mock_conn.name = "multi"
    mock_conn.is_configured.return_value = True
    mock_conn.search.return_value = [lead_csv, lead_auto]

    with patch('app.discovery.search_service.get_connector', return_value=mock_conn):
        service.execute_search_job(job.id)

    b_csv = autonomous_db.scalars(select(Business).where(Business.domain == "alphaexports.in")).first()
    b_auto = autonomous_db.scalars(select(Business).where(Business.domain == "betaclinic.in")).first()

    assert "CSV Import" in b_csv.source
    assert "Autonomous Discovery" in b_auto.source
    assert "OpenStreetMap" in b_auto.source
