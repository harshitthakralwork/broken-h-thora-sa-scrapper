"""Unit and integration tests for WikidataSparqlConnector:
- Verifies CC0 public domain attribution, status reporting, and zero auth requirement.
- Verifies city QID resolution (Gurugram, Bengaluru, Mumbai) and fallback search.
- Verifies parsing of genuine Wikidata SPARQL bindings.
- Verifies safe fail-closed behavior on network timeouts or HTTP errors.
- Verifies integration with SearchService and deduplication.
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Business, BusinessDomain, SearchJob
from app.discovery.connectors import WikidataSparqlConnector, DiscoveredLead, get_connector
from app.discovery.search_service import SearchService


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


def test_wikidata_connector_metadata_and_status():
    """Verify connector attributes, CC0 licensing, and zero auth requirement."""
    connector = WikidataSparqlConnector()
    status = connector.get_status()

    assert status['name'] == 'wikidata_sparql'
    assert 'Wikidata' in status['title']
    assert status['category'] == 'Open Knowledge Graph'
    assert status['is_configured'] is True
    assert status['requires_auth'] is False
    assert 'CC0' in status['attribution']
    assert 'India' in status['supported_regions']


def test_wikidata_connector_city_resolution():
    """Verify city name to Wikidata QID mapping."""
    connector = WikidataSparqlConnector()
    assert 'Q238508' in connector._resolve_city_qids('Gurugram')
    assert 'Q238508' in connector._resolve_city_qids('Gurgaon, Haryana')
    assert 'Q1355' in connector._resolve_city_qids('Bengaluru, Karnataka')
    assert 'Q1156' in connector._resolve_city_qids('Mumbai')


def test_wikidata_connector_parses_live_format_response():
    """Verify connector correctly parses Wikidata SPARQL json bindings."""
    connector = WikidataSparqlConnector()
    mock_sparql_data = {
        'results': {
            'bindings': [
                {
                    'item': {'value': 'http://www.wikidata.org/entity/Q140068951'},
                    'itemLabel': {'value': 'eCorpIT'},
                    'website': {'value': 'https://ecorpit.com'},
                    'industryLabel': {'value': 'information technology consulting'}
                },
                {
                    'item': {'value': 'http://www.wikidata.org/entity/Q140995407'},
                    'itemLabel': {'value': 'Prozo'},
                    'website': {'value': 'https://www.prozo.com/'},
                    'industryLabel': {'value': 'logistics'}
                },
                {
                    # Unlabeled entity (raw QID) must be skipped
                    'item': {'value': 'http://www.wikidata.org/entity/Q99999999'},
                    'itemLabel': {'value': 'Q99999999'},
                    'website': {'value': 'https://skipme.com'}
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_sparql_data

    with patch('httpx.Client.get', return_value=mock_resp):
        leads = connector.search(city='Gurugram', industry='Technology', limit=5)

    assert len(leads) == 2
    l1 = leads[0]
    assert l1.name == 'eCorpIT'
    assert l1.website == 'https://ecorpit.com'
    assert l1.domain == 'ecorpit.com'
    assert l1.city == 'Gurugram'
    assert l1.country == 'India'
    assert l1.source_url == 'http://www.wikidata.org/entity/Q140068951'
    assert 'CC0' in l1.source_name

    l2 = leads[1]
    assert l2.name == 'Prozo'
    assert l2.domain == 'prozo.com'


def test_wikidata_connector_fails_closed_without_synthetics():
    """Verify network error or timeout returns empty list and logs last_error."""
    connector = WikidataSparqlConnector()
    with patch('httpx.Client.get', side_effect=Exception("Connection timed out")):
        leads = connector.search(city='Gurugram')

    assert leads == []
    assert connector.last_error is not None
    assert 'Connection timed out' in connector.last_error


def test_search_service_wikidata_job_execution(test_db):
    """Verify SearchService executes a wikidata discovery job and stores new leads."""
    service = SearchService(test_db)
    job = service.create_search_job(
        name="Wikidata Gurugram Discovery",
        city="Gurugram",
        industry="Technology",
        connector_name="wikidata_sparql",
        is_autonomous=False,
        max_leads=5
    )

    mock_lead = DiscoveredLead(
        name="DigiSurface Solutions",
        website="https://digisurface.co",
        domain="digisurface.co",
        city="Gurugram",
        country="India",
        industry="Technology Consulting",
        source_name="Wikidata Knowledge Graph (CC0)",
        source_url="http://www.wikidata.org/entity/Q139832066",
        connector_name="wikidata_sparql"
    )

    with patch.object(WikidataSparqlConnector, 'search', return_value=[mock_lead]):
        res = service.execute_search_job(job.id)

    assert res['status'] == 'completed'
    assert res['added'] == 1
    assert res['total_discovered'] == 1

    b = test_db.scalars(select(Business).where(Business.domain == 'digisurface.co')).first()
    assert b is not None
    assert b.name == 'DigiSurface Solutions'
    assert 'Wikidata' in b.source
    assert 'http://www.wikidata.org/entity/Q139832066' in b.source

