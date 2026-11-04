"""Regression and unit tests for India-First Multi-Source Lead Discovery.
Covers:
- BaseConnector attribution and supported_regions reporting
- WebsiteCrawlerConnector safety and execution
- Company name legal suffix normalization for deduplication
- Indian metro and regional resolution
- Multi-provider discovery execution and partial-success tolerance
- Cautious deduplication and physical branch separation
- Preserving empty domains as SQL NULL
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

try:
    from backend.app.models import Base, Business, BusinessDomain, SearchJob, BusinessProfile
    from backend.app.discovery.connectors import (
        BaseConnector,
        DiscoveredLead,
        CONNECTOR_REGISTRY,
        get_connector,
        list_all_connectors,
        WebsiteCrawlerConnector,
        OpenStreetMapOverpassConnector
    )
    from backend.app.discovery.search_service import (
        SearchService,
        normalize_company_name_key,
        resolve_indian_metro,
        INDIAN_METROS
    )
except ImportError:
    from app.models import Base, Business, BusinessDomain, SearchJob, BusinessProfile
    from app.discovery.connectors import (
        BaseConnector,
        DiscoveredLead,
        CONNECTOR_REGISTRY,
        get_connector,
        list_all_connectors,
        WebsiteCrawlerConnector,
        OpenStreetMapOverpassConnector
    )
    from app.discovery.search_service import (
        SearchService,
        normalize_company_name_key,
        resolve_indian_metro,
        INDIAN_METROS
    )


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_base_connector_attribution_and_supported_regions():
    """Verify all registered connectors report attribution and supported_regions."""
    connectors = list_all_connectors()
    assert len(connectors) >= 11

    osm = get_connector('osm_overpass')
    assert osm is not None
    osm_status = osm.get_status()
    assert 'attribution' in osm_status
    assert 'OpenStreetMap' in osm_status['attribution']
    assert 'India' in osm_status['supported_regions']

    crawler = get_connector('website_crawler')
    assert crawler is not None
    crawler_status = crawler.get_status()
    assert 'attribution' in crawler_status
    assert 'Public Website' in crawler_status['attribution']
    assert 'India' in crawler_status['supported_regions']


def test_company_legal_suffix_normalization():
    """Verify legal entity suffixes are stripped for matching while preserving core brand name."""
    cases = [
        ("Acme Technologies Pvt Ltd", "acme technologies"),
        ("Acme Technologies Private Limited", "acme technologies"),
        ("Acme Technologies Pvt. Ltd.", "acme technologies"),
        ("Infosys Limited", "infosys"),
        ("Infosys Ltd", "infosys"),
        ("Swiggy Bundl Technologies LLP", "swiggy bundl technologies"),
        ("Zomato Media Corp.", "zomato media"),
        ("Freshworks Inc.", "freshworks"),
        ("Reliance Retail Enterprises", "reliance retail"),
        ("Tata Consultancy Services Solutions", "tata consultancy services")
    ]
    for raw, expected in cases:
        assert normalize_company_name_key(raw) == expected, f"Failed on {raw}"


def test_indian_metro_resolution():
    """Verify Indian metropolitan areas resolve their canonical state and name."""
    bengaluru = resolve_indian_metro("Bengaluru")
    assert bengaluru is not None
    assert bengaluru['state'] == 'Karnataka'
    assert bengaluru['name'] == 'Bengaluru'

    bangalore = resolve_indian_metro("bangalore")
    assert bangalore is not None
    assert bangalore['state'] == 'Karnataka'

    mumbai = resolve_indian_metro("Mumbai")
    assert mumbai is not None
    assert mumbai['state'] == 'Maharashtra'

    delhi = resolve_indian_metro("New Delhi")
    assert delhi is not None
    assert delhi['state'] == 'Delhi NCR'

    hyderabad = resolve_indian_metro("Hyderabad")
    assert hyderabad is not None
    assert hyderabad['state'] == 'Telangana'


def test_website_crawler_connector_empty_query():
    """Website crawler connector should return empty list gracefully when no URLs provided."""
    crawler = WebsiteCrawlerConnector()
    leads = crawler.search(query="just generic words", country="India", city="Bengaluru")
    assert leads == []


def test_website_crawler_connector_simulated_crawl(test_db):
    """Website crawler connector parses valid HTML, runs qualification, and returns high-evidence lead."""
    crawler = WebsiteCrawlerConnector()
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Apex Logistics India - Freight & Supply Chain</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="description" content="Leading cold-chain logistics in Bengaluru, India.">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Apex Logistics India",
            "email": "operations@apexlogistics.in",
            "telephone": "+91-80-41234567"
        }
        </script>
    </head>
    <body>
        <a href="mailto:contact@apexlogistics.in">Contact Us</a>
        <a href="tel:+918041234567">+91 80 4123 4567</a>
        <form action="/quote"><input type="text" name="origin"/></form>
    </body>
    </html>
    """

    import sys
    crawl_mods = []
    for mod_name in ['app.crawl_client', 'backend.app.crawl_client']:
        if mod_name in sys.modules:
            crawl_mods.append(sys.modules[mod_name])
    if not crawl_mods:
        try:
            import app.crawl_client as m; crawl_mods.append(m)
        except ImportError:
            pass
        try:
            import backend.app.crawl_client as m; crawl_mods.append(m)
        except ImportError:
            pass

    from contextlib import ExitStack
    with ExitStack() as stack:
        for m in crawl_mods:
            stack.enter_context(patch.object(m, 'run_crawl', return_value=('https://apexlogistics.in', sample_html)))
        leads = crawler.search(query="https://apexlogistics.in", country="India", city="Bengaluru")
        assert len(leads) == 1
        lead = leads[0]
        assert "Apex Logistics India" in lead.name
        assert lead.domain == "apexlogistics.in"
        assert lead.website == "https://apexlogistics.in"
        assert lead.city == "Bengaluru"
        assert lead.email == "operations@apexlogistics.in" or lead.email == "contact@apexlogistics.in"
        assert lead.phone == "+91-80-41234567" or "+918041234567" in lead.phone
        assert lead.connector_name == "website_crawler"
        assert lead.evidence_confidence in ('high', 'medium')
        assert 'qual_data' in lead.raw_metadata
        # Check all 9 services scored
        opportunities = lead.raw_metadata['qual_data'].get('opportunities', [])
        assert len(opportunities) == 9


def test_multi_source_execution_with_partial_success(test_db):
    """Verify multi-provider discovery succeeds partially if one provider times out but another returns leads."""
    service = SearchService(test_db)
    job = service.create_search_job(
        name="Multi-Source Bengaluru Test",
        query="Logistics",
        country="India",
        city="Bengaluru",
        connector_name="osm_overpass,website_crawler",
        max_leads=10
    )

    lead_crawler = DiscoveredLead(
        name="FastTrack Logistics Pvt Ltd",
        website="https://fasttracklogistics.in",
        domain="fasttracklogistics.in",
        country="India",
        city="Bengaluru",
        connector_name="website_crawler"
    )

    # Simulate Overpass timing out (504) while crawler succeeds
    with patch.object(OpenStreetMapOverpassConnector, 'search', side_effect=Exception("HTTP 504 Gateway Timeout")), \
         patch.object(WebsiteCrawlerConnector, 'search', return_value=[lead_crawler]):

        result = service.execute_search_job(job.id)
        assert result['status'] == 'partial_success'
        assert result['added'] == 1
        assert result['total_discovered'] == 1
        assert result['per_provider_counts']['website_crawler'] == 1
        assert '504' in result['provider_errors']['osm_overpass']

        # Database record should be stored
        biz = test_db.scalars(select(Business).where(Business.name == "FastTrack Logistics Pvt Ltd")).first()
        assert biz is not None
        assert biz.domain == "fasttracklogistics.in"


def test_branch_separation_cautious_deduplication(test_db):
    """Verify distinct physical branches of a business are preserved and NOT merged when lacking domains."""
    service = SearchService(test_db)

    # Lead 1: Indiranagar branch
    lead1 = DiscoveredLead(
        name="Third Wave Coffee Roasters",
        website="",
        domain="",
        country="India",
        city="Indiranagar, Bengaluru",
        connector_name="osm_overpass"
    )

    # Lead 2: Koramangala branch (different location)
    lead2 = DiscoveredLead(
        name="Third Wave Coffee Roasters",
        website="",
        domain="",
        country="India",
        city="Koramangala, Bengaluru",
        connector_name="osm_overpass"
    )

    job1 = service.create_search_job(name="Branch 1", connector_name="osm_overpass")
    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=[lead1]):
        res1 = service.execute_search_job(job1.id)
        assert res1['added'] == 1

    job2 = service.create_search_job(name="Branch 2", connector_name="osm_overpass")
    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=[lead2]):
        res2 = service.execute_search_job(job2.id)
        assert res2['added'] == 1  # Should be preserved as separate branch, NOT merged!

    businesses = test_db.scalars(select(Business).where(Business.name == "Third Wave Coffee Roasters")).all()
    assert len(businesses) == 2
    assert {b.location for b in businesses} == {"Indiranagar, Bengaluru, India", "Koramangala, Bengaluru, India"}


def test_empty_domains_stored_as_sql_null(test_db):
    """Verify businesses without domains store None in SQL, never empty strings."""
    service = SearchService(test_db)
    lead = DiscoveredLead(
        name="Local Bengaluru Kirana",
        website="",
        domain="",
        country="India",
        city="Bengaluru",
        connector_name="osm_overpass"
    )

    job = service.create_search_job(name="Kirana Job", connector_name="osm_overpass")
    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=[lead]):
        res = service.execute_search_job(job.id)
        assert res['added'] == 1

    biz = test_db.scalars(select(Business).where(Business.name == "Local Bengaluru Kirana")).first()
    assert biz is not None
    assert biz.domain is None

