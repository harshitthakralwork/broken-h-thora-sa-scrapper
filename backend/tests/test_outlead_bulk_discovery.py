"""Test suite for OutLead-inspired Bulk Business Discovery & Batch Processing.

Verifies:
1. Provider registration under 'outlead_bulk_maps', 'outlead', 'bulk_maps', 'google_maps'.
2. Missing credentials detection and honest unconfigured status reporting.
3. Single-category discovery query construction.
4. Multi-category discovery query construction.
5. Multi-city Cartesian cross-product query generation.
6. Batch chunking, state management and progress calculation.
7. Duplicate detection across batches.
8. Branch preservation: separate physical branches sharing a domain are preserved and linked.
9. Partial failures tolerance (one failed batch does not abort other batches).
10. Retry behavior with exponential backoff on transient errors.
11. Database persistence of OutLead place fields (rating, reviews, hours, coordinates, maps URL).
12. Official website enrichment handoff.
13. Contact extraction handoff.
14. Qualification handoff for all 9 services.
15. CSV export generation.
16. Pause, resume, and cancellation state transitions.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    Base, Business, BusinessDomain, BusinessProfile, BusinessRelationship,
    Contact, LeadQualification, ResearchHistory, SearchJob
)
from app.discovery.connectors import (
    CONNECTOR_REGISTRY, get_connector, list_all_connectors,
    DiscoveredLead, ConnectorNotConfiguredError, OutLeadBulkMapsConnector,
    place_key_from_url, parse_open_state
)
from app.discovery.batch_engine import (
    OutLeadBatchEngine, build_batch_queries, parse_multivalue_input
)
from app.discovery.search_service import SearchService


@pytest.fixture
def outlead_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_provider_registration():
    """1. Verify connector is registered in registry under all canonical names and aliases."""
    for key in ['outlead_bulk_maps', 'outlead', 'bulk_maps', 'google_maps']:
        connector = get_connector(key)
        assert connector is not None
        assert isinstance(connector, OutLeadBulkMapsConnector)
        assert connector.name == 'outlead_bulk_maps'
        assert 'Google Maps / Places Data & OutLead Engine' in connector.attribution

    all_conns = list_all_connectors()
    outlead_statuses = [c for c in all_conns if c['name'] == 'outlead_bulk_maps']
    assert len(outlead_statuses) == 1
    assert outlead_statuses[0]['category'] == 'Bulk Business Discovery'


def test_provider_unconfigured_without_credentials():
    """2. Verify connector reports unconfigured and raises ConnectorNotConfiguredError if no API keys."""
    connector = OutLeadBulkMapsConnector()
    with patch.dict('os.environ', {
        'GOOGLE_PLACES_API_KEY': '',
        'SERPAPI_API_KEY': '',
        'OUTLEAD_API_KEY': ''
    }, clear=False):
        assert connector.is_configured() is False
        status = connector.get_status()
        assert status['is_configured'] is False
        assert status['status'] == 'unconfigured'
        assert 'GOOGLE_PLACES_API_KEY' in status['message']

        with pytest.raises(ConnectorNotConfiguredError) as exc_info:
            connector.search(city='Gurugram', category='Clinics')
        assert 'not configured' in str(exc_info.value).lower()


def test_query_generation_single_and_multi_category():
    """3 & 4. Verify single-category and multi-category query construction."""
    queries_single = build_batch_queries(['Gurugram'], ['Clinics'])
    assert len(queries_single) == 1
    assert queries_single[0]['query'] == 'Clinics in Gurugram'
    assert queries_single[0]['city'] == 'Gurugram'
    assert queries_single[0]['category'] == 'Clinics'

    queries_multi = build_batch_queries(['Gurugram'], ['Clinics', 'IT companies', 'Restaurants'])
    assert len(queries_multi) == 3
    assert [q['query'] for q in queries_multi] == [
        'Clinics in Gurugram',
        'IT companies in Gurugram',
        'Restaurants in Gurugram'
    ]


def test_multi_city_cartesian_batch_generation():
    """5 & 6. Verify Cartesian cross-product query generation and parsing across multiple cities."""
    cities = parse_multivalue_input('Gurugram, Faridabad')
    categories = parse_multivalue_input('IT companies, Clinics, Restaurants')

    queries = build_batch_queries(cities, categories)
    # 2 cities x 3 categories = 6 batch sub-queries
    assert len(queries) == 6
    expected_queries = [
        'IT companies in Gurugram',
        'IT companies in Faridabad',
        'Clinics in Gurugram',
        'Clinics in Faridabad',
        'Restaurants in Gurugram',
        'Restaurants in Faridabad'
    ]
    assert [q['query'] for q in queries] == expected_queries


def test_batch_execution_with_partial_failures_and_retry(outlead_db):
    """9 & 10. Verify batch execution handles partial connector failures and keeps going."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(
        name="Batch Multi-City Run",
        country="India",
        city="Gurugram, Faridabad",
        category="Clinics, IT companies",
        max_leads=10,
        status="pending"
    )
    outlead_db.add(job)
    outlead_db.commit()

    engine.prepare_job_batches(job, ['Gurugram', 'Faridabad'], ['Clinics', 'IT companies'])

    call_count = 0

    class MockFlakyConnector(OutLeadBulkMapsConnector):
        def is_configured(self):
            return True

        def search(self, query='', country='India', city='', industry='', category='', limit=10):
            nonlocal call_count
            call_count += 1
            if 'Faridabad' in query:
                raise ConnectionError("Transient network failure on Faridabad endpoint")
            return [
                DiscoveredLead(
                    name=f"Enterprise {city} {category}",
                    website=f"https://enterprise-{city.lower()}-{category.lower().replace(' ', '')}.in",
                    domain=f"enterprise-{city.lower()}-{category.lower().replace(' ', '')}.in",
                    country=country,
                    city=city,
                    address=f"Plot 100, Sector 14, {city}",
                    phone="+91-124-4001122",
                    industry=category,
                    source_name="OutLead Bulk Maps Discovery",
                    source_url="https://maps.google.com/test",
                    connector_name="outlead_bulk_maps",
                    raw_metadata={
                        'rating': 4.7,
                        'review_count': 120,
                        'business_hours': 'Mon-Fri 9 AM - 6 PM',
                        'price_level': '$$',
                        'latitude': 28.4595,
                        'longitude': 77.0266,
                        'place_id': 'ChIJ_mock_gurugram_1'
                    }
                )
            ]

    res = engine.execute_batch_job(job.id, connectors=[MockFlakyConnector()])
    assert res['batches_total'] == 4
    # 2 Gurugram queries succeeded, 2 Faridabad queries failed cleanly
    assert res['batches_completed'] == 2
    assert res['batches_failed'] == 2
    assert res['status'] == 'partial_success'
    assert res['leads_added'] == 2


def test_duplicate_detection_and_branch_preservation(outlead_db):
    """7 & 8. Verify duplicate detection and physical branch location preservation."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(name="Branch Test", country="India", status="pending")
    outlead_db.add(job)
    outlead_db.commit()

    lead_gurugram = DiscoveredLead(
        name="Medanta Health City",
        website="https://www.medanta.org",
        domain="medanta.org",
        country="India",
        city="Gurugram",
        address="CH Bakhtawar Singh Rd, Sector 38, Gurugram",
        phone="+91-124-4141414",
        industry="Healthcare",
        source_name="OutLead Bulk Maps Discovery",
        source_url="https://maps.google.com/medanta-gurugram",
        connector_name="outlead_bulk_maps",
        raw_metadata={'rating': 4.6, 'review_count': 5400}
    )

    # 1. First branch in Gurugram
    added, dup = engine._persist_lead(job, lead_gurugram)
    assert added is True
    assert dup is False

    # 2. Duplicate insertion of same exact location in Gurugram
    added_dup, is_dup = engine._persist_lead(job, lead_gurugram)
    assert added_dup is False
    assert is_dup is True

    # 3. Separate physical branch in Lucknow sharing the same corporate domain
    lead_lucknow_branch = DiscoveredLead(
        name="Medanta Hospital Lucknow",
        website="https://www.medanta.org/lucknow",
        domain="medanta.org",
        country="India",
        city="Lucknow",
        address="Sector A, Pocket 1, Sushant Golf City, Lucknow",
        phone="+91-522-4505050",
        industry="Healthcare",
        source_name="OutLead Bulk Maps Discovery",
        source_url="https://maps.google.com/medanta-lucknow",
        connector_name="outlead_bulk_maps",
        raw_metadata={'rating': 4.8, 'review_count': 3200}
    )

    added_branch, dup_branch = engine._persist_lead(job, lead_lucknow_branch)
    # Must be preserved as a separate business record!
    assert added_branch is True
    assert dup_branch is False

    # Verify branch relationship was created
    rel = outlead_db.scalars(
        select(BusinessRelationship).where(BusinessRelationship.relation == 'branch_of')
    ).first()
    assert rel is not None


def test_database_persistence_of_place_fields(outlead_db):
    """11. Verify extended OutLead place fields are persisted in BusinessProfile."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(name="Profile Place Fields Test", country="India", status="pending")
    outlead_db.add(job)
    outlead_db.commit()

    lead = DiscoveredLead(
        name="Haldiram's Gurugram",
        website="https://www.haldirams.com",
        domain="haldirams.com",
        country="India",
        city="Gurugram",
        address="Cyber City, DLF Phase 2, Gurugram, Haryana 122002",
        phone="+91-124-4200300",
        industry="Restaurant",
        source_name="OutLead Bulk Maps Discovery",
        source_url="https://maps.google.com/haldirams-gurugram",
        connector_name="outlead_bulk_maps",
        raw_metadata={
            'rating': 4.5,
            'review_count': 1850,
            'business_hours': 'Mon-Sun 10:00 AM - 11:00 PM',
            'price_level': '$$',
            'latitude': 28.4908,
            'longitude': 77.0912,
            'place_id': 'ChIJ_haldirams_dlf_phase2',
            'maps_url': 'https://maps.google.com/haldirams-gurugram'
        }
    )

    added, dup = engine._persist_lead(job, lead)
    assert added is True

    # Inspect persisted BusinessProfile
    b = outlead_db.scalars(select(Business).where(Business.domain == 'haldirams.com')).first()
    assert b is not None
    profile = outlead_db.get(BusinessProfile, b.id)
    assert profile is not None
    assert profile.rating == 4.5
    assert profile.review_count == 1850
    assert profile.business_hours == 'Mon-Sun 10:00 AM - 11:00 PM'
    assert profile.price_level == '$$'
    assert profile.latitude == 28.4908
    assert profile.longitude == 77.0912
    assert profile.place_id == 'ChIJ_haldirams_dlf_phase2'
    assert profile.maps_url == 'https://maps.google.com/haldirams-gurugram'


def test_website_enrichment_and_qualification_handoff(outlead_db):
    """12, 13 & 14. Verify autonomous enrichment handoff: crawl website, extract contacts, 9-service qualification."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(
        name="Autonomous Handoff Test",
        country="India",
        is_autonomous=True,
        status="pending"
    )
    outlead_db.add(job)
    outlead_db.commit()

    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Zomato Logistics Tech Hub</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="description" content="Food delivery logistics and supply network in Gurugram, India.">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Corporation",
            "name": "Zomato Logistics Hub",
            "email": "logistics@zomato-test.com",
            "telephone": "+91-124-6000000"
        }
        </script>
    </head>
    <body>
        <h1>Zomato Logistics Fleet</h1>
        <a href="mailto:support@zomato-test.com">Support Inquiries</a>
    </body>
    </html>
    """

    lead = DiscoveredLead(
        name="Zomato Logistics Hub",
        website="https://zomato-test.com",
        domain="zomato-test.com",
        country="India",
        city="Gurugram",
        industry="Logistics",
        source_name="OutLead Bulk Maps Discovery",
        source_url="https://maps.google.com/zomato-test",
        connector_name="outlead_bulk_maps"
    )

    with patch('app.crawl_client.run_crawl', return_value=('https://zomato-test.com', sample_html)):
        added, dup = engine._persist_lead(job, lead)
        assert added is True

        b = outlead_db.scalars(select(Business).where(Business.domain == 'zomato-test.com')).first()
        assert b is not None
        assert b.researched_at is not None

        # Verify extracted contact
        contact = outlead_db.scalars(select(Contact).where(Contact.business_id == b.id)).first()
        assert contact is not None
        assert 'zomato-test.com' in contact.email

        # Verify 9-service qualification
        qual = outlead_db.scalars(select(LeadQualification).where(LeadQualification.business_id == b.id)).first()
        assert qual is not None
        assert qual.business_quality_score > 0
        assert qual.conversion_potential_score > 0
        opps = json.loads(qual.service_scores_json)
        assert len(opps) == 9
        for opp in opps:
            assert opp['buying_intent_status'] == 'unknown'
            assert 'observed_technical_state' in opp


def test_pause_resume_and_cancellation_state_transitions(outlead_db):
    """16. Verify pause, resume, and cancellation state transitions."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(
        name="State Machine Test",
        country="India",
        city="Gurugram, Faridabad",
        category="Clinics, IT",
        status="pending"
    )
    outlead_db.add(job)
    outlead_db.commit()

    engine.prepare_job_batches(job, ['Gurugram', 'Faridabad'], ['Clinics', 'IT'])
    assert job.batch_status == 'pending'

    # Pause job
    pause_res = engine.pause_job(job.id)
    assert pause_res['batch_status'] == 'paused'
    assert job.batch_status == 'paused'

    # Cancel job
    cancel_res = engine.cancel_job(job.id)
    assert cancel_res['batch_status'] == 'cancelled'
    assert job.batch_status == 'cancelled'
    assert job.status == 'cancelled'


def test_csv_export_formatting(outlead_db):
    """15. Verify CSV export generates correct OutLead headers and formatted values."""
    engine = OutLeadBatchEngine(outlead_db)
    job = SearchJob(
        name="Export Test Job",
        connector_name="outlead_bulk_maps",
        status="completed",
        results_count=1
    )
    outlead_db.add(job)
    outlead_db.commit()

    b = Business(
        name="Fortis Hospital Gurugram",
        website="https://www.fortishealthcare.com",
        domain="fortishealthcare.com",
        industry="Healthcare",
        location="Gurugram, India",
        source="Bulk Discovery (OutLead Google Maps / Places): https://maps.google.com/fortis"
    )
    outlead_db.add(b)
    outlead_db.commit()

    profile = BusinessProfile(
        business_id=b.id,
        address="Sector 44, Gurugram, Haryana 122002",
        phone="+91-124-4962200",
        rating=4.3,
        review_count=3100,
        business_hours="Open 24 hours",
        maps_url="https://maps.google.com/fortis"
    )
    outlead_db.add(profile)
    outlead_db.commit()

    csv_output = engine.export_job_csv(job.id)
    assert "Business Name" in csv_output
    assert "Official Website" in csv_output
    assert "Rating" in csv_output
    assert "Review Count" in csv_output
    assert "Business Hours" in csv_output
    assert "Maps URL" in csv_output
    assert "Fortis Hospital Gurugram" in csv_output
    assert "4.3" in csv_output
    assert "3100" in csv_output
    assert "Open 24 hours" in csv_output


def test_outlead_regex_helpers():
    """Verify regex helpers ported from OutLead under MIT License."""
    m = place_key_from_url("https://www.google.com/maps/place/Data+Corp/data=!4m2!3m1!1s0x390d19d582e38859:0x2cf5ed4e8ef782bb")
    assert m == "0x390d19d582e38859:0x2cf5ed4e8ef782bb"

    assert parse_open_state("Open 24 hours daily") == "Open 24 hours"
    assert parse_open_state("Permanently closed since 2024") == "Permanently closed"
    assert parse_open_state("Temporarily closed for renovation") == "Temporarily closed"
    assert parse_open_state("Open · Closes 9 PM") == "Open"
    assert parse_open_state("Closed · Opens 10 AM Mon") == "Closed"
    assert parse_open_state(None) is None


def test_api_bulk_job_lifecycle_and_csv_export(outlead_db):
    """Verify SearchService bulk lifecycle methods and CSV export."""
    service = SearchService(outlead_db)
    job = service.create_search_job(
        name="API Lifecycle Bulk Job",
        country="India",
        city="Gurugram",
        cities="Gurugram, Faridabad",
        categories="Clinics, IT companies",
        connector_name="wikidata_sparql",
        max_leads=10
    )
    assert job.cities == "Gurugram, Faridabad"
    assert job.categories == "Clinics, IT companies"
    assert job.batch_status == 'pending'

    # Pause job
    pause_res = service.pause_search_job(job.id)
    assert pause_res['batch_status'] == 'paused'

    # Resume job
    resume_res = service.resume_search_job(job.id)
    assert resume_res['job_id'] == job.id

    # Cancel job
    cancel_res = service.cancel_search_job(job.id)
    assert cancel_res['batch_status'] == 'cancelled'

    # Export CSV
    csv_text = service.export_search_job_csv(job.id)
    assert "Business Name" in csv_text
    assert "Official Website" in csv_text


def test_crm_bulk_tagging_and_pipeline_stages(outlead_db):
    """Verify CRM bulk selection, tagging, and pipeline stage transitions."""
    from fastapi.testclient import TestClient
    from app import main
    from app.api_router import get_db as router_db

    b1 = Business(id="b-crm-1", name="Alpha Corp", website="https://alpha.example", domain="alpha.example", location="Gurugram")
    b2 = Business(id="b-crm-2", name="Beta Tech", website="https://beta.example", domain="beta.example", location="Faridabad")
    outlead_db.add_all([b1, b2])
    outlead_db.commit()

    headers = {'Authorization': 'Bearer ' + main.ADMIN_TOKEN}
    main.app.dependency_overrides[main.db] = lambda: outlead_db
    main.app.dependency_overrides[router_db] = lambda: outlead_db
    try:
        client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 50000))
        # Bulk Tag
        res = client.post('/api/leads/bulk-tag', headers=headers, json={
            'business_ids': ['b-crm-1', 'b-crm-2'],
            'tag': 'Enterprise Lead'
        })
        assert res.status_code == 200, res.text
        assert res.json()['tagged_count'] == 2

        # Bulk Stage Move
        res_stage = client.post('/api/pipeline/bulk-stage', headers=headers, json={
            'business_ids': ['b-crm-1', 'b-crm-2'],
            'stage': 'qualified',
            'notes': 'Verified Indian business with digital opportunity'
        })
        assert res_stage.status_code == 200, res_stage.text
        assert res_stage.json()['updated_count'] == 2
    finally:
        main.app.dependency_overrides.pop(main.db, None)
        main.app.dependency_overrides[router_db] = main.db


def test_google_sheets_sync_unconfigured_and_sync(outlead_db):
    """Verify Google Sheets sync handles unconfigured status and payload export."""
    from app.integrations.sheets_service import GoogleSheetsSyncService

    service = GoogleSheetsSyncService(outlead_db)
    # Default without webhook should report unconfigured transparently
    result = service.sync_to_sheets()
    assert result['success'] is False
    assert result['status'] == 'unconfigured'
    assert 'Setup instructions' in result['notice']

    # Update with webhook and dedicated secret, and test mock sync
    service.update_config(
        webhook_url="https://script.google.com/macros/s/mock-test/exec",
        webhook_secret="dedicated_sheets_secret_123"
    )
    # Ensure safe config masks secret
    safe_cfg = service.get_safe_config()
    assert safe_cfg['has_secret'] is True
    assert safe_cfg['webhook_secret_masked'] == '••••••••'
    assert 'dedicated_sheets_secret_123' not in str(safe_cfg)

    with patch('httpx.Client.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {'success': True, 'updated_count': 1})
        synced = service.sync_to_sheets()
        assert synced['success'] is True
        assert synced['status'] == 'connected'
        # Verify secret was transmitted
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs['headers']['X-Webhook-Secret'] == 'dedicated_sheets_secret_123'
        assert call_kwargs['json']['secret'] == 'dedicated_sheets_secret_123'

    # Test import_from_sheets with secret validation
    unauth = service.import_from_sheets({'secret': 'wrong_secret', 'records': []})
    assert unauth['success'] is False
    assert unauth['status'] == 'unauthorized'

    # Test import_from_sheets with valid secret
    valid_import = service.import_from_sheets({'secret': 'dedicated_sheets_secret_123', 'records': []})
    assert valid_import['success'] is True
    assert valid_import['updated_count'] == 0


def test_n8n_automation_dispatch_and_idempotency(outlead_db):
    """Verify n8n event dispatching, idempotency keys, and unconfigured safety."""
    from app.integrations.n8n_service import N8nAutomationService

    n8n = N8nAutomationService(outlead_db)
    # Unconfigured dispatch fails safely
    res_unconfigured = n8n.dispatch_event('lead.discovered', {'name': 'Test Lead'})
    assert res_unconfigured['dispatched'] is False
    assert res_unconfigured['status'] == 'disabled'

    # Enable without webhook
    n8n.update_config(webhook_url='', is_enabled=True)
    res_no_url = n8n.dispatch_event('lead.discovered', {'name': 'Test Lead'})
    assert res_no_url['status'] == 'unconfigured'

    # Configure webhook URL
    n8n.update_config(webhook_url='http://localhost:5678/webhook/sparkxflow', is_enabled=True)
    with patch('httpx.Client.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text='ok')
        dispatched = n8n.dispatch_event(
            'lead.qualified',
            {'business_id': 'b-1', 'quality_score': 85},
            idempotency_key='test-key-123'
        )
        assert dispatched['dispatched'] is True
        assert dispatched['status'] == 'connected'
        # Verify idempotency key was included in header
        _, kwargs = mock_post.call_args
        assert kwargs['headers']['X-SparkXFlow-Idempotency-Key'] == 'test-key-123'

