"""Integration and Unit Tests for Modular Live-Source Connectors and Real Contact Intelligence.
Verifies that:
- Connectors report accurate configured vs unconfigured status based on environment.
- Unconfigured sources fail closed with clear status without fabricating data.
- Official UK Companies House, Google Custom Search, and OpenCorporates parse real response schemas accurately when mocked.
- Real public contacts are extracted from crawled HTML Schema.org and mailto/tel tags.
- No synthetic or guessed contacts/emails are ever created.
"""
import json
import os
import httpx
import pytest
from unittest.mock import patch, MagicMock

from app.discovery.connectors import (
    CompaniesHouseRegistryConnector,
    GoogleSearchConnector,
    SerpApiConnector,
    OpenCorporatesConnector,
    CsvSourceConnector,
    PublicDirectoryConnector,
    WebQueryConnector,
    IndiaOpenGovDataConnector,
    OpenStreetMapOverpassConnector,
    SecEdgarConnector,
    DiscoveredLead,
    ConnectorNotConfiguredError,
    list_all_connectors,
    get_connector
)
from app.discovery.search_service import SearchService
from app.models import SearchJob
from app.research.qualification_engine import QualificationEngine
from app.contacts.contact_service import ContactService
from app.models import Base, Business, BusinessProfile, Contact
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_connector_status_reporting():
    """Verify connectors correctly report their configuration status and required keys."""
    statuses = list_all_connectors()
    assert len(statuses) >= 6

    csv_status = next(s for s in statuses if s['name'] == 'csv_file')
    assert csv_status['is_configured'] is True
    assert csv_status['status'] == 'available'

    # Without env vars, auth-required connectors must report unconfigured
    with patch.dict(os.environ, {}, clear=True):
        ch = CompaniesHouseRegistryConnector()
        assert ch.is_configured() is False
        assert ch.get_status()['status'] == 'unconfigured'
        assert 'COMPANIES_HOUSE_API_KEY' in ch.get_status()['auth_keys']

        google = GoogleSearchConnector()
        assert google.is_configured() is False
        assert google.get_status()['status'] == 'unconfigured'

def test_unconfigured_connector_fails_closed():
    """Ensure searching an unconfigured connector raises ConnectorNotConfiguredError and returns no fake data."""
    with patch.dict(os.environ, {'COMPANIES_HOUSE_API_KEY': ''}):
        ch = CompaniesHouseRegistryConnector()
        with pytest.raises(ConnectorNotConfiguredError):
            ch.search(query='Logistics')

    with patch.dict(os.environ, {'GOOGLE_SEARCH_API_KEY': '', 'GOOGLE_SEARCH_CX': ''}):
        google = GoogleSearchConnector()
        with pytest.raises(ConnectorNotConfiguredError):
            google.search(query='Logistics')

def test_companies_house_mock_integration():
    """Verify Companies House connector parses official UK registry response accurately."""
    mock_response = {
        'items': [
            {
                'title': 'VANGUARD HAULAGE & LOGISTICS LIMITED',
                'company_number': '09876543',
                'company_status': 'active',
                'company_type': 'ltd',
                'address_snippet': '14 Commercial Road, London, E1 6LP',
                'address': {
                    'locality': 'London',
                    'region': 'Greater London',
                    'country': 'United Kingdom'
                },
                'description': '09876543 - Incorporated on 12 March 2015'
            }
        ]
    }

    with patch.dict(os.environ, {'COMPANIES_HOUSE_API_KEY': 'test_fake_key_12345'}):
        ch = CompaniesHouseRegistryConnector()
        with patch('httpx.Client.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_get.return_value = mock_resp

            leads = ch.search(query='Haulage London')
            assert len(leads) == 1
            lead = leads[0]
            assert lead.name == 'VANGUARD HAULAGE & LOGISTICS LIMITED'
            assert lead.city == 'London'
            assert lead.country == 'United Kingdom'
            assert lead.address == '14 Commercial Road, London, E1 6LP'
            assert '09876543' in lead.source_url
            assert lead.source_name == 'UK Companies House Public Register'
            assert lead.evidence_confidence == 'high'

def test_google_custom_search_mock_integration():
    """Verify Google Search connector parses search engine response accurately."""
    mock_google_response = {
        'items': [
            {
                'title': 'Apex Software Solutions | Official Site',
                'link': 'https://www.apexsoftware.co.uk',
                'displayLink': 'www.apexsoftware.co.uk',
                'snippet': 'Bespoke web application development and cloud systems consultancy in Manchester, UK.'
            }
        ]
    }

    with patch.dict(os.environ, {'GOOGLE_SEARCH_API_KEY': 'fake_key', 'GOOGLE_SEARCH_CX': 'fake_cx'}):
        google = GoogleSearchConnector()
        with patch('httpx.Client.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_google_response
            mock_get.return_value = mock_resp

            leads = google.search(query='Web apps Manchester')
            assert len(leads) == 1
            lead = leads[0]
            assert lead.name == 'Apex Software Solutions' # Cleaned suffix
            assert lead.website == 'https://www.apexsoftware.co.uk'
            assert lead.domain == 'www.apexsoftware.co.uk'
            assert lead.source_name == 'Google Search Index'

def test_extract_public_contacts_from_html():
    """Verify that actual public contacts are extracted from HTML Schema.org and mailto/tel tags."""
    html_with_contacts = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>TechFlow Systems</title>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "Evelyn Reed",
            "jobTitle": "Co-Founder & CEO",
            "email": "evelyn@techflow.io",
            "telephone": "+44 20 7123 4567",
            "sameAs": "https://www.linkedin.com/in/evelynreed-techflow"
        }
        </script>
    </head>
    <body>
        <h1>Welcome</h1>
        <p>Get in touch with our team: <a href="mailto:support@techflow.io">support@techflow.io</a></p>
        <p>Call us at <a href="tel:+442079998888">+44 20 7999 8888</a></p>
    </body>
    </html>
    """

    contacts = QualificationEngine.extract_public_contacts("https://techflow.io", html_with_contacts, "TechFlow Systems")
    assert len(contacts) >= 2

    # Check Schema.org contact
    exec_contact = next(c for c in contacts if c['full_name'] == 'Evelyn Reed')
    assert exec_contact['job_title'] == 'Co-Founder & CEO'
    assert exec_contact['role_category'] == 'founder'
    assert exec_contact['email'] == 'evelyn@techflow.io'
    assert exec_contact['phone'] == '+44 20 7123 4567'
    assert exec_contact['verification_status'] == 'unverified_public'
    assert 'Schema.org' in exec_contact['contact_source']

    # Check mailto contact
    support_contact = next(c for c in contacts if c['email'] == 'support@techflow.io')
    assert support_contact['verification_status'] == 'unverified_public'

def test_extract_public_contacts_empty_when_none_present():
    """Verify that when HTML contains no public contacts, an empty list is returned and NO fake contacts are created."""
    bare_html = "<html><head><title>Simple Site</title></head><body><p>Just plain text content without contact links.</p></body></html>"
    contacts = QualificationEngine.extract_public_contacts("https://plain.example.com", bare_html, "Plain Co")
    assert contacts == []

def test_contact_service_never_fabricates_mock_executives(test_db):
    """Verify ContactService does not generate mock 'Executive Office' or 'director@...' when none exist."""
    biz = Business(
        name="Empty Contacts Enterprise",
        website="https://empty.example.com",
        domain="empty.example.com",
        source="Manual test"
    )
    test_db.add(biz)
    test_db.commit()

    service = ContactService(test_db)
    discovered = service.discover_public_decision_makers(biz.id)
    # Must be empty because no website crawl or corporate registry records exist
    assert discovered == []
    # Verify no contacts in DB
    assert test_db.query(Contact).count() == 0


def test_india_ogd_connector_disabled_by_default():
    """Verify India Open Government Data connector is optional, disabled by default, and fails closed safely."""
    with patch.dict(os.environ, {'DATA_GOV_IN_API_KEY': ''}):
        ogd = IndiaOpenGovDataConnector()
        assert ogd.is_configured() is False
        status = ogd.get_status()
        assert status['status'] == 'unconfigured'
        assert status['requires_auth'] is True
        assert 'DATA_GOV_IN_API_KEY' in status['auth_keys']

        # Calling search must raise ConnectorNotConfiguredError without fabricating data
        with pytest.raises(ConnectorNotConfiguredError) as exc_info:
            ogd.search(query='Technology', city='Bengaluru')
        assert "DATA_GOV_IN_API_KEY" in str(exc_info.value)
        assert "currently disabled" in str(exc_info.value)


def test_osm_overpass_connector_active_and_free():
    """Verify OpenStreetMap Overpass connector is 100% free, requires no auth, and parses real Indian POI data."""
    osm = OpenStreetMapOverpassConnector()
    assert osm.is_configured() is True
    assert osm.requires_auth is False
    assert osm.get_status()['status'] == 'available'

    mock_osm_response = {
        "elements": [
            {
                "type": "node",
                "id": 11012347336,
                "tags": {
                    "name": "Badshah Logistics India Pvt Ltd",
                    "office": "logistics",
                    "addr:city": "Mumbai",
                    "addr:country": "India",
                    "website": "https://www.badshahlogistics.com",
                    "phone": "+91 9320320499",
                    "email": "info@badshahlogistics.com"
                }
            }
        ]
    }

    with patch('httpx.Client.post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_osm_response
        mock_post.return_value = mock_resp

        leads = osm.search(query="Logistics", city="Mumbai", country="India")
        assert len(leads) == 1
        lead = leads[0]
        assert lead.name == "Badshah Logistics India Pvt Ltd"
        assert lead.website == "https://www.badshahlogistics.com"
        assert lead.city == "Mumbai"
        assert lead.country == "India"
        assert lead.phone == "+91 9320320499"
        assert lead.email == "info@badshahlogistics.com"
        assert "11012347336" in lead.source_url
        assert "OpenStreetMap" in lead.source_name
        assert lead.evidence_confidence == "high"


def test_osm_overpass_handles_empty_or_failed_queries_without_synthetic_generation():
    """Verify OpenStreetMap connector returns empty list on network error or zero matches, never generating fake leads."""
    osm = OpenStreetMapOverpassConnector()
    with patch('httpx.Client.post', side_effect=httpx.TimeoutException("Overpass connection timed out")):
        leads = osm.search(query="NonExistentFirm123", country="India")
        assert leads == []


def test_search_job_india_ogd_disabled_fails_closed_safely(test_db):
    """Verify search job with disabled India OGD records unconfigured status and never inserts fake data."""
    job = SearchJob(
        name="Test India OGD Job",
        connector_name="india_ogd",
        query="Technology",
        country="India",
        status="pending",
        max_leads=10
    )
    test_db.add(job)
    test_db.commit()

    with patch.dict(os.environ, {'DATA_GOV_IN_API_KEY': ''}):
        service = SearchService(test_db)
        res = service.execute_search_job(job.id)
        assert res['status'] == 'unconfigured'
        assert res['added'] == 0
        assert res['total_discovered'] == 0
        # Verify job is failed and has error_log
        updated_job = test_db.get(SearchJob, job.id)
        assert updated_job.status == 'failed'
        assert "DATA_GOV_IN_API_KEY" in updated_job.error_log
        # Verify zero fake businesses created
        assert test_db.query(Business).count() == 0


def test_opencorporates_india_jurisdiction_applied():
    """Verify OpenCorporates searches with country='India' target jurisdiction_code='in' when licence is configured."""
    with patch.dict(os.environ, {'OPENCORPORATES_API_KEY': 'test_licence_key'}):
        oc = OpenCorporatesConnector()
        with patch('httpx.Client.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'results': {'companies': []}}
            mock_get.return_value = mock_resp

            oc.search(query='Tata', country='India')
            assert mock_get.called
            called_params = mock_get.call_args[1].get('params', {})
            assert called_params.get('jurisdiction_code') == 'in'


def test_sec_edgar_connector_configured_and_parses_response():
    """Verify US SEC EDGAR connector parses official EFTS disclosure filings accurately."""
    mock_edgar_response = {
        'hits': {
            'hits': [
                {
                    '_source': {
                        'entity_name': 'Unique Logistics International, Inc.',
                        'display_names': ['Unique Logistics International, Inc.  (UNQL)  (CIK 0001281845)'],
                        'ciks': ['0001281845'],
                        'sic_description': 'Freight Transportation Arrangement',
                        'form': '10-K'
                    }
                }
            ]
        }
    }

    with patch.dict(os.environ, {'SEC_USER_AGENT': 'SparkXFlowLeadEngine/1.0 contact:sample@example.com'}):
        sec = SecEdgarConnector()
        assert sec.is_configured() is True
        assert sec.get_status()['status'] == 'available'

        with patch('httpx.Client.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_edgar_response
            mock_get.return_value = mock_resp

            leads = sec.search(query='Logistics')
            assert len(leads) == 1
            lead = leads[0]
            assert lead.name == 'Unique Logistics International, Inc.'
            assert lead.country == 'United States'
            assert lead.source_name == 'US SEC EDGAR Public Company Disclosures'
            assert '0001281845' in lead.source_url
            assert lead.evidence_confidence == 'high'
            assert lead.raw_metadata['ticker'] == 'UNQL'


def test_sec_edgar_connector_fails_closed_without_user_agent():
    """Verify US SEC EDGAR connector fails closed if SEC_USER_AGENT is not provided."""
    with patch.dict(os.environ, {'SEC_USER_AGENT': ''}):
        sec = SecEdgarConnector()
        assert sec.is_configured() is False
        assert sec.get_status()['status'] == 'unconfigured'
        with pytest.raises(ConnectorNotConfiguredError):
            sec.search(query='Logistics')


def test_opencorporates_licensing_note():
    """Verify OpenCorporates connector documents ODbL and commercial licensing requirements."""
    oc = OpenCorporatesConnector()
    status = oc.get_status()
    assert 'Licence Required' in status['title'] or 'ODbL' in status['description']
    assert 'commercial' in status['description'].lower()
    # Without key, must be unconfigured
    assert oc.is_configured() is False


def test_multiple_businesses_empty_and_null_domains_safe(test_db):
    """P0 Regression: Ensure multiple businesses with missing, empty, or NULL domains do not trigger SQL unique constraint crashes."""
    service = SearchService(test_db)
    job = SearchJob(name="Empty Domains Test", connector_name="osm_overpass")
    test_db.add(job)
    test_db.commit()

    # Mock connector returning 3 businesses with no website / empty domains
    mock_leads = [
        DiscoveredLead(name="Shop Alpha", website="", domain="", city="Bengaluru", country="India", connector_name="osm_overpass"),
        DiscoveredLead(name="Warehouse Beta", website="", domain="", city="Bengaluru", country="India", connector_name="osm_overpass"),
        DiscoveredLead(name="Clinic Gamma", website="", domain="", city="Bengaluru", country="India", connector_name="osm_overpass"),
    ]

    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=mock_leads):
        res = service.execute_search_job(job.id)
        assert res['status'] == 'completed'
        assert res['added'] == 3
        assert res['total_discovered'] == 3

    # Verify all 3 exist in DB and their domains are SQL NULL (None)
    records = test_db.query(Business).all()
    assert len(records) == 3
    for b in records:
        assert b.domain is None


def test_duplicate_actual_domains_deduplicated(test_db):
    """P0 Regression: Ensure actual non-empty domains preserve unique protection and are deduplicated."""
    service = SearchService(test_db)
    job = SearchJob(name="Duplicate Domain Test", connector_name="osm_overpass")
    test_db.add(job)
    test_db.commit()

    mock_leads = [
        DiscoveredLead(name="Logistics Apex", website="https://apexlogistics.in", domain="apexlogistics.in", city="Bengaluru", country="India"),
        DiscoveredLead(name="Logistics Apex Branch", website="https://apexlogistics.in", domain="apexlogistics.in", city="Bengaluru", country="India"),
    ]

    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=mock_leads):
        res = service.execute_search_job(job.id)
        assert res['status'] == 'completed'
        assert res['added'] == 1
        assert res['duplicates_flagged_for_review'] == 1

    records = test_db.query(Business).filter(Business.domain == 'apexlogistics.in').all()
    assert len(records) == 1


def test_two_different_physical_businesses_without_websites_not_merged(test_db):
    """P0 Regression: Ensure two distinct physical businesses with no websites are NOT merged simply because they lack domains."""
    service = SearchService(test_db)
    job = SearchJob(name="Distinct Physical Businesses Test", connector_name="osm_overpass")
    test_db.add(job)
    test_db.commit()

    mock_leads = [
        DiscoveredLead(name="Indiranagar Bakery", website="", domain="", city="Indiranagar, Bengaluru", country="India"),
        DiscoveredLead(name="Whitefield Pharmacy", website="", domain="", city="Whitefield, Bengaluru", country="India"),
    ]

    with patch.object(OpenStreetMapOverpassConnector, 'search', return_value=mock_leads):
        res = service.execute_search_job(job.id)
        assert res['added'] == 2

    records = test_db.query(Business).all()
    assert len(records) == 2
    names = {b.name for b in records}
    assert "Indiranagar Bakery" in names
    assert "Whitefield Pharmacy" in names


def test_connector_aliases_resolve_to_same_instance():
    """P1 Regression: Ensure osm_overpass, overpass, and openstreetmap aliases all resolve to the same connector."""
    c1 = get_connector('osm_overpass')
    c2 = get_connector('overpass')
    c3 = get_connector('openstreetmap')
    c4 = get_connector('  OVERPASS  ')

    assert c1 is not None
    assert c1 is c2
    assert c2 is c3
    assert c3 is c4


def test_unknown_connector_returns_clear_error_without_silent_fallback(test_db):
    """P1 Regression: Ensure an unknown connector name raises a clear error and does NOT silently fall back to an unrelated connector."""
    service = SearchService(test_db)
    job = SearchJob(name="Unknown Connector Test", connector_name="totally_unknown_provider")
    test_db.add(job)
    test_db.commit()

    res = service.execute_search_job(job.id)
    assert res['status'] == 'failed'
    assert 'Unknown discovery connector' in res['error']

    updated_job = test_db.get(SearchJob, job.id)
    assert updated_job.status == 'failed'
    assert 'Unknown discovery connector' in updated_job.error_log


# --- Overpass.ch Integration Readiness Tests ---

def test_overpass_default_provider_is_public_overpass():
    """Verify that default provider is public_overpass, requiring no auth and keeping existing behavior."""
    with patch.dict(os.environ, {'OVERPASS_PROVIDER': '', 'OVERPASS_CH_API_KEY': ''}):
        osm = OpenStreetMapOverpassConnector()
        assert osm.get_configured_provider() == OpenStreetMapOverpassConnector.PROVIDER_PUBLIC
        assert osm.is_configured() is True
        st = osm.get_status()
        assert st['status'] == 'available'
        assert st['requires_auth'] is False
        assert st['auth_keys'] == []
        assert 'Overpass.ch' not in st['title']


def test_overpass_ch_unconfigured_when_key_missing():
    """Verify that OVERPASS_PROVIDER=overpass_ch without API key reports unconfigured and fails closed."""
    with patch.dict(os.environ, {'OVERPASS_PROVIDER': 'overpass_ch', 'OVERPASS_CH_API_KEY': ''}):
        osm = OpenStreetMapOverpassConnector()
        assert osm.get_configured_provider() == OpenStreetMapOverpassConnector.PROVIDER_OVERPASS_CH
        assert osm.is_configured() is False
        st = osm.get_status()
        assert st['status'] == 'unconfigured'
        assert st['requires_auth'] is True
        assert st['auth_keys'] == ['OVERPASS_CH_API_KEY']
        assert 'Overpass.ch' in st['title']

        # Calling search must raise ConnectorNotConfiguredError without fabricating data
        with pytest.raises(ConnectorNotConfiguredError) as exc_info:
            osm.search(query='Logistics', city='Bengaluru')
        assert "OVERPASS_CH_API_KEY" in str(exc_info.value)
        assert "unconfigured" in str(exc_info.value)


def test_overpass_ch_configured_and_formats_endpoint_correctly():
    """Verify Overpass.ch endpoint URL format and query execution when configured."""
    fake_key = 'test_secret_ch_key_12345'
    mock_response = {
        'elements': [
            {
                'type': 'node',
                'id': 987654321,
                'tags': {
                    'name': 'Bengaluru Express Cargo',
                    'office': 'logistics',
                    'addr:city': 'Bengaluru',
                    'addr:country': 'India',
                    'website': 'https://www.bengalurucargo.example.com',
                    'phone': '+91 80 1234 5678',
                    'email': 'contact@bengalurucargo.example.com'
                }
            }
        ]
    }

    with patch.dict(os.environ, {
        'OVERPASS_PROVIDER': 'overpass_ch',
        'OVERPASS_CH_API_KEY': fake_key
    }):
        osm = OpenStreetMapOverpassConnector()
        osm.reset_cache_and_usage()
        assert osm.is_configured() is True
        st = osm.get_status()
        assert st['status'] == 'available'
        assert st['requires_auth'] is True

        with patch('httpx.Client.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            leads = osm.search(query='Logistics', city='Bengaluru', country='India')
            assert len(leads) == 1
            lead = leads[0]

            # Verify POST was sent to the official Overpass.ch endpoint format
            assert mock_post.called
            called_endpoint = mock_post.call_args[0][0]
            assert called_endpoint == f"https://api.overpass.ch/v1/{fake_key}/interpreter"

            # Lead assertions
            assert lead.name == 'Bengaluru Express Cargo'
            assert lead.website == 'https://www.bengalurucargo.example.com'
            assert lead.city == 'Bengaluru'
            assert lead.country == 'India'
            assert 'Overpass.ch' in lead.source_name
            assert 'ODbL' in lead.source_name


def test_overpass_ch_never_leaks_api_key_in_leads_or_urls():
    """Security verification: Verify API key is NEVER stored in source_url, description, or raw_metadata."""
    fake_key = 'super_secret_overpass_token_99999'
    mock_response = {
        'elements': [
            {
                'type': 'node',
                'id': 1234567,
                'tags': {
                    'name': 'Secure Freight Services',
                    'office': 'logistics'
                }
            }
        ]
    }

    with patch.dict(os.environ, {
        'OVERPASS_PROVIDER': 'overpass_ch',
        'OVERPASS_CH_API_KEY': fake_key
    }):
        osm = OpenStreetMapOverpassConnector()
        osm.reset_cache_and_usage()

        with patch('httpx.Client.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            leads = osm.search(query='Freight', city='Bengaluru')
            assert len(leads) == 1
            lead = leads[0]

            # The key MUST NEVER be in lead fields
            assert fake_key not in lead.source_url
            assert lead.source_url == 'https://www.openstreetmap.org/node/1234567'
            assert fake_key not in lead.description
            assert fake_key not in str(lead.raw_metadata)


def test_overpass_ch_error_codes_handling_and_fail_closed():
    """Verify that HTTP 401, 403, 429, 503, 504 are handled gracefully and return [] without fabricating data."""
    fake_key = 'test_key'
    with patch.dict(os.environ, {
        'OVERPASS_PROVIDER': 'overpass_ch',
        'OVERPASS_CH_API_KEY': fake_key
    }):
        osm = OpenStreetMapOverpassConnector()
        osm.reset_cache_and_usage()

        # 1. HTTP 401 Unauthorized
        err_401 = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=MagicMock(status_code=401))
        with patch('httpx.Client.post', side_effect=err_401):
            assert osm.search(query='Test401', city='Bengaluru') == []

        # 2. HTTP 403 Forbidden / Quota
        err_403 = httpx.HTTPStatusError("Forbidden", request=MagicMock(), response=MagicMock(status_code=403))
        with patch('httpx.Client.post', side_effect=err_403):
            assert osm.search(query='Test403', city='Bengaluru') == []

        # 3. HTTP 429 Rate Limit with Retry-After
        resp_429 = MagicMock(status_code=429, headers={'Retry-After': '60'})
        err_429 = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=resp_429)
        with patch('httpx.Client.post', side_effect=err_429):
            assert osm.search(query='Test429', city='Bengaluru') == []

        # 4. HTTP 504 Gateway Timeout
        resp_504 = MagicMock(status_code=504)
        err_504 = httpx.HTTPStatusError("Gateway timeout", request=MagicMock(), response=resp_504)
        with patch('httpx.Client.post', side_effect=err_504):
            assert osm.search(query='Test504', city='Bengaluru') == []


def test_overpass_ch_monthly_budget_cap_and_caching():
    """Verify that monthly budget cap halts queries and in-memory caching prevents duplicate billing."""
    fake_key = 'test_key'
    mock_response = {
        'elements': [
            {'type': 'node', 'id': 111, 'tags': {'name': 'Fast Logistics', 'office': 'logistics'}}
        ]
    }

    with patch.dict(os.environ, {
        'OVERPASS_PROVIDER': 'overpass_ch',
        'OVERPASS_CH_API_KEY': fake_key,
        'OVERPASS_CH_MONTHLY_BUDGET': '2'
    }):
        osm = OpenStreetMapOverpassConnector()
        osm.reset_cache_and_usage()

        with patch('httpx.Client.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response
            mock_post.return_value = mock_resp

            # Query 1 (uses 1 request from budget)
            leads1 = osm.search(query='Logistics', city='Bengaluru')
            assert len(leads1) == 1
            assert mock_post.call_count == 1
            assert osm.get_monthly_requests_used() == 1

            # Query 1 repeated: served from in-memory cache, does NOT call HTTP or increment budget!
            leads1_cached = osm.search(query='Logistics', city='Bengaluru')
            assert len(leads1_cached) == 1
            assert mock_post.call_count == 1  # Unchanged!
            assert osm.get_monthly_requests_used() == 1  # Unchanged!

            # Query 2 (different query -> uses 2nd request, reaches budget)
            leads2 = osm.search(query='Warehousing', city='Bengaluru')
            assert len(leads2) == 1
            assert mock_post.call_count == 2
            assert osm.get_monthly_requests_used() == 2

            # Query 3 (exceeds budget of 2 -> halted safely before making HTTP call!)
            leads3 = osm.search(query='Shipping', city='Bengaluru')
            assert leads3 == []
            assert mock_post.call_count == 2  # No HTTP call made!


def test_overpass_redact_url_utility():
    """Verify URL redaction utility properly masks secret API keys."""
    raw = "https://api.overpass.ch/v1/super_secret_key_abcdef12345/interpreter"
    redacted = OpenStreetMapOverpassConnector._redact_url(raw)
    assert "super_secret_key" not in redacted
    assert redacted == "https://api.overpass.ch/v1/[REDACTED]/interpreter"




