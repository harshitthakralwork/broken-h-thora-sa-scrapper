"""Comprehensive test suite for SparkXFlow Intelligence Platform.
Validates Market Discovery, Research Qualification, Contact Intelligence,
Human Approval Center for Outreach, Suppression, and Integrations.
"""
import json
import pytest
from sqlalchemy.engine import URL
from fastapi.testclient import TestClient
from app import main
from app.models import (
    Business, BusinessProfile, LeadQualification, Contact, Campaign,
    OutreachMessage, InboxMessage, FollowUpTask, SuppressionEntry,
    SystemIntegration, SearchJob
)
from app.research.qualification_engine import QualificationEngine
from app.outreach.personalization import EmailPersonalizer
from app.outreach.approval_service import ApprovalService, compute_approval_hash

client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 50000))
headers = {'Authorization': 'Bearer ' + main.ADMIN_TOKEN}

@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    old_engine = main.engine
    engine = main.create_engine(
        URL.create('sqlite', database=(tmp_path / 'platform-test.db').as_posix()),
        connect_args={'check_same_thread': False}
    )
    main.engine = engine
    main.SessionLocal.configure(bind=engine)
    main.Base.metadata.create_all(engine)
    with main.SessionLocal() as session:
        session.add(main.IdentityGuard(id='global', counter=0))
        session.add(main.CrawlerControl(id='global', counter=0))
        session.commit()
    yield
    engine.dispose()
    main.engine = old_engine
    main.SessionLocal.configure(bind=old_engine)

from unittest.mock import patch
from app.discovery.connectors import DiscoveredLead

def test_market_and_discovery_jobs():
    # Test listing connectors
    res = client.get('/api/discovery/connectors', headers=headers)
    assert res.status_code == 200
    connectors = res.json()
    assert len(connectors) >= 2
    assert any(c['name'] == 'public_directory' for c in connectors)

    # Test creating and executing a search job with mocked registry source
    job_payload = {
        'name': 'B2B Logistics UK',
        'query': 'logistics warehouse',
        'country': 'United Kingdom',
        'city': 'Birmingham',
        'industry': 'Supply Chain & Logistics',
        'target_service': 'AI Automation',
        'max_leads': 3,
        'connector_name': 'public_directory'
    }
    mock_leads = [
        DiscoveredLead(
            name="Vanguard Haulage Ltd",
            website="https://vanguardhaulage.co.uk",
            domain="vanguardhaulage.co.uk",
            industry="Supply Chain & Logistics",
            country="United Kingdom",
            city="Birmingham",
            source_name="Public Business Directory",
            source_url="https://find-and-update.company-information.service.gov.uk/company/09876543",
            connector_name="public_directory"
        )
    ]
    with patch('app.discovery.connectors.PublicDirectoryConnector.search', return_value=mock_leads):
        create_res = client.post('/api/discovery/jobs', headers=headers, json=job_payload)
        assert create_res.status_code == 200
        data = create_res.json()
        assert data['job']['status'] == 'completed'
        assert data['result']['added'] >= 1

    # Verify discovered leads in DB
    leads_res = client.get('/api/leads', headers=headers)
    assert leads_res.status_code == 200
    leads = leads_res.json()
    assert len(leads) >= 1

    # Test market overview
    mkt = client.get('/api/market/overview', headers=headers).json()
    assert mkt['total_discovered_leads'] >= 1
    assert len(mkt['target_services']) == 9

def test_qualification_engine_9_services():
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>OmniCorp Commercial Construction</title>
        <!-- Missing viewport tag -->
        <!-- Missing meta description -->
    </head>
    <body>
        <h1>Welcome to OmniCorp</h1>
        <form action="/quote" method="POST">
            <input name="name" />
            <button type="submit">Request Quote</button>
        </form>
    </body>
    </html>
    """
    analysis = QualificationEngine.analyze("https://omnicorp.example", html_sample, "OmniCorp")
    assert len(analysis['opportunities']) == 9
    services = [o['service'] for o in analysis['opportunities']]
    assert "Website Development" in services
    assert "AI Automation" in services
    assert "SEO and Digital Marketing" in services

    # Website Development score should be elevated due to missing viewport
    web_dev = next(o for o in analysis['opportunities'] if o['service'] == 'Website Development')
    assert web_dev['score'] >= 70
    assert analysis['business_quality'] > 0
    assert analysis['conversion_potential'] > 0

def test_contact_intelligence():
    # Create lead
    lead = client.post('/api/leads', headers=headers, json={
        'name': 'Apex Medical Solutions',
        'website': 'https://apexmedical.co',
        'industry': 'Healthcare'
    }).json()
    lead_id = lead['id']

    # Auto-discover contacts before crawl: cleanly returns 0 (never fabricates contacts)
    disc_res = client.post(f'/api/leads/{lead_id}/contacts/discover', headers=headers)
    assert disc_res.status_code == 200
    assert disc_res.json()['discovered_count'] == 0

    # Simulate real observed contact from website crawl
    obs_contacts = [{
        'full_name': 'Dr. Robert Apex',
        'job_title': 'Managing Director',
        'role_category': 'managing_director',
        'email': 'robert@apexmedical.co',
        'phone': '+1 555 1234',
        'contact_source': 'Observed on public website: https://apexmedical.co'
    }]
    from app.contacts.contact_service import ContactService
    with main.SessionLocal() as session:
        ContactService(session).save_observed_contacts(lead_id, obs_contacts)

    # Manually add a verified contact
    contact_res = client.post(f'/api/leads/{lead_id}/contacts', headers=headers, json={
        'full_name': 'Dr. Sarah Connor',
        'job_title': 'Chief Technology Officer',
        'role_category': 'tech',
        'email': 'sarah@apexmedical.co',
        'phone': '+1 555 9876'
    })
    assert contact_res.status_code == 200

    # Verify contacts list contains both observed and manually added contact
    contacts = client.get(f'/api/leads/{lead_id}/contacts', headers=headers).json()
    assert len(contacts) == 2
    assert any(c['full_name'] == 'Dr. Robert Apex' for c in contacts)
    assert any(c['full_name'] == 'Dr. Sarah Connor' for c in contacts)

def test_email_outreach_approval_center():
    # Create lead and contact
    lead = client.post('/api/leads', headers=headers, json={
        'name': 'Zenith Cloud Inc',
        'website': 'https://zenithcloud.io',
        'industry': 'Technology'
    }).json()

    # Generate personalized outreach draft
    draft_res = client.post('/api/outreach/generate', headers=headers, json={
        'business_id': lead['id'],
        'target_service': 'AI Automation'
    })
    assert draft_res.status_code == 200
    msg = draft_res.json()
    assert msg['status'] == 'pending_approval'
    assert 'AI Automation' in msg['subject']
    msg_id = msg['id']

    # Transmission MUST fail with HTTP 400 while pending approval
    unapproved_send = client.post(f'/api/outreach/messages/{msg_id}/send', headers=headers)
    assert unapproved_send.status_code == 400

    # Approve message
    appr_res = client.post(f'/api/outreach/messages/{msg_id}/approve', headers=headers)
    assert appr_res.status_code == 200
    assert appr_res.json()['status'] == 'approved'

    # If message is edited, approval MUST be automatically revoked
    edit_res = client.put(f'/api/outreach/messages/{msg_id}/edit', headers=headers, json={
        'subject': 'Updated: Quick question for Zenith Cloud',
        'body_text': 'Hi, just following up with updated partnership details.'
    })
    assert edit_res.status_code == 200
    assert edit_res.json()['status'] == 'pending_approval'

    # Re-approve
    client.post(f'/api/outreach/messages/{msg_id}/approve', headers=headers)

    # Enable sending integration and send
    client.post('/api/integrations/sending/toggle?enabled=true', headers=headers)
    send_res = client.post(f'/api/outreach/messages/{msg_id}/send', headers=headers)
    assert send_res.status_code == 200
    assert send_res.json()['success'] is True

    # Test idempotency: second send attempt should return 400
    duplicate_send = client.post(f'/api/outreach/messages/{msg_id}/send', headers=headers)
    assert duplicate_send.status_code == 400

def test_suppression_and_inbox_unsubscribe():
    # Simulate inbound unsubscribe reply
    sim_res = client.post('/api/inbox/simulate-reply', headers=headers, json={
        'sender_email': 'unsubscribe-prospect@domain.com',
        'recipient_email': 'outreach@sparkxflow.agency',
        'subject': 'Please stop emailing',
        'body': 'Please unsubscribe me and remove me from your list immediately.'
    })
    assert sim_res.status_code == 200
    assert sim_res.json()['classification'] == 'unsubscribe'

    # Verify recipient was automatically added to suppression list
    sup_res = client.get('/api/suppression', headers=headers)
    assert sup_res.status_code == 200
    suppressed = sup_res.json()
    assert any(s['email'] == 'unsubscribe-prospect@domain.com' for s in suppressed)

def test_dashboard_stats_real_data():
    stats = client.get('/api/dashboard/stats', headers=headers).json()
    assert 'total_discovered' in stats
    assert 'emails_awaiting_approval' in stats
    assert 'conversion_rate_pct' in stats
    assert stats['failed_jobs'] >= 0
