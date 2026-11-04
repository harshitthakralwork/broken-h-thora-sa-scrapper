"""Expanded API router for SparkXFlow Intelligence Platform.
Exposes endpoints for Market Intelligence, Lead Intelligence, Contact Intelligence,
Email Outreach with Human Approval Center, Sales Pipeline, Integrations and Automations.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from .models import (
    Business, BusinessProfile, LeadQualification, Contact, SearchJob, DiscoveryHypothesis,
    SourceConnector, Campaign, OutreachMessage, InboxMessage, FollowUpTask, SuppressionEntry,
    SalesPipelineItem, SystemIntegration, AutomationJob, DuplicateReview, ImportBatch, now, uid
)
from .discovery.search_service import SearchService, SPARKXFLOW_SERVICES, TARGET_GEOGRAPHIES
from .discovery.connectors import CONNECTOR_REGISTRY
from .contacts.contact_service import ContactService
from .outreach.personalization import EmailPersonalizer
from .outreach.approval_service import ApprovalService
from .outreach.inbox_service import InboxService
from .outreach.followup_service import FollowUpService
from .integrations.sheets_service import GoogleSheetsSyncService
from .integrations.n8n_service import N8nAutomationService
from .automation.job_coordinator import AutomationCoordinator

logger = logging.getLogger('sparkxflow.api')
router = APIRouter()

# Dependency placeholder (injected from main.py)
def get_db():
    from .main import db
    yield from db()

# --- Pydantic Schemas ---
class SearchJobIn(BaseModel):
    name: str = Field(default='', max_length=255)
    query: str = Field(default='', max_length=255)
    country: str = Field(default='India', max_length=100)
    city: str = Field(default='Bengaluru', max_length=100)
    state: str = Field(default='', max_length=100)
    industry: str = Field(default='', max_length=120)
    category: str = Field(default='', max_length=120)
    target_service: str = Field(default='Website Development', max_length=120)
    max_leads: int = Field(default=25, ge=1, le=500)
    is_autonomous: bool = Field(default=False)
    connector_name: str = Field(default='all_available', max_length=100)
    # OutLead-inspired bulk discovery parameters
    cities: Optional[Any] = None
    categories: Optional[Any] = None

class ContactIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    job_title: str = Field(default='', max_length=200)
    role_category: str = Field(default='other', max_length=50)
    email: str = Field(default='', max_length=255)
    phone: str = Field(default='', max_length=100)
    linkedin_url: str = Field(default='', max_length=2048)

class ProfileIn(BaseModel):
    sub_industry: str = Field(default='', max_length=120)
    country: str = Field(default='', max_length=100)
    city: str = Field(default='', max_length=100)
    address: str = Field(default='', max_length=500)
    phone: str = Field(default='', max_length=100)
    email: str = Field(default='', max_length=255)
    description: str = Field(default='')

class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_audience: str = Field(default='', max_length=255)
    selected_services: List[str] = Field(default_factory=list)
    target_countries: List[str] = Field(default_factory=list)
    target_industries: List[str] = Field(default_factory=list)

class DraftGenerateIn(BaseModel):
    business_id: str
    contact_id: Optional[str] = None
    target_service: str = "Website Development"
    campaign_id: Optional[str] = None

class MessageEditIn(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1)

class SimulateReplyIn(BaseModel):
    sender_email: str
    recipient_email: str
    subject: str
    body: str
    outreach_message_id: Optional[str] = None

class PipelineUpdateIn(BaseModel):
    stage: str
    deal_value: float = 0.0
    priority: str = 'medium'
    notes: str = ''

class N8nConfigIn(BaseModel):
    webhook_url: str = Field(default='', max_length=2048)
    is_enabled: bool = True
    events: Optional[List[str]] = None

class GoogleSheetsConfigIn(BaseModel):
    webhook_url: str = Field(default='', max_length=2048)
    sheet_id: str = Field(default='', max_length=100)
    webhook_secret: Optional[str] = Field(default=None, max_length=255)
    is_enabled: bool = True

class BulkTagIn(BaseModel):
    business_ids: List[str]
    tag: str = Field(min_length=1, max_length=100)

class BulkStageIn(BaseModel):
    business_ids: List[str]
    stage: str = Field(min_length=1, max_length=50)
    notes: Optional[str] = ''

# --- Engine A & B: Discovery & Market Intelligence ---

@router.get('/discovery/jobs')
def list_search_jobs(session: Session = Depends(get_db)):
    jobs = session.scalars(select(SearchJob).order_by(SearchJob.created_at.desc())).all()
    return [{
        'id': j.id,
        'name': j.name,
        'query': j.query,
        'country': j.country,
        'city': j.city,
        'industry': j.industry,
        'category': j.category,
        'target_service': j.target_service,
        'max_leads': j.max_leads,
        'status': j.status,
        'progress': j.progress,
        'results_count': j.results_count,
        'is_autonomous': j.is_autonomous,
        'connector_name': j.connector_name,
        'error_log': j.error_log,
        'cities': j.cities,
        'categories': j.categories,
        'batch_params': j.batch_params,
        'batch_status': j.batch_status,
        'created_at': j.created_at.isoformat(),
        'updated_at': j.updated_at.isoformat()
    } for j in jobs]

@router.post('/discovery/jobs')
def create_search_job(item: SearchJobIn, session: Session = Depends(get_db)):
    service = SearchService(session)
    effective_city = item.city
    if item.state and item.state.lower() not in (item.city or '').lower():
        effective_city = f"{item.city}, {item.state}".strip(', ')
    job = service.create_search_job(
        name=item.name,
        query=item.query,
        country=item.country,
        city=effective_city,
        industry=item.industry,
        category=item.category,
        target_service=item.target_service,
        max_leads=item.max_leads,
        is_autonomous=item.is_autonomous,
        connector_name=item.connector_name,
        cities=item.cities,
        categories=item.categories
    )
    # Execute synchronously for reliable user feedback
    result = service.execute_search_job(job.id)
    return {'job': {
        'id': job.id,
        'name': job.name,
        'status': job.status,
        'batch_status': job.batch_status,
        'results_count': job.results_count
    }, 'result': result}

@router.post('/discovery/jobs/{job_id}/execute')
def execute_job(job_id: str, session: Session = Depends(get_db)):
    service = SearchService(session)
    return service.execute_search_job(job_id)

@router.post('/discovery/jobs/{job_id}/pause')
def pause_discovery_job(job_id: str, session: Session = Depends(get_db)):
    service = SearchService(session)
    return service.pause_search_job(job_id)

@router.post('/discovery/jobs/{job_id}/resume')
def resume_discovery_job(job_id: str, session: Session = Depends(get_db)):
    service = SearchService(session)
    return service.resume_search_job(job_id)

@router.post('/discovery/jobs/{job_id}/cancel')
def cancel_discovery_job(job_id: str, session: Session = Depends(get_db)):
    service = SearchService(session)
    return service.cancel_search_job(job_id)

@router.get('/discovery/jobs/{job_id}/export/csv')
def export_discovery_job_csv(job_id: str, session: Session = Depends(get_db)):
    from fastapi.responses import Response
    service = SearchService(session)
    csv_data = service.export_search_job_csv(job_id)
    return Response(
        content=csv_data,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="sparkxflow-discovery-{job_id}.csv"'}
    )

@router.get('/discovery/connectors')
def list_connectors():
    from .discovery.connectors import list_all_connectors
    return list_all_connectors()

@router.get('/discovery/hypotheses')
def list_hypotheses(session: Session = Depends(get_db)):
    service = SearchService(session)
    hyps = session.scalars(select(DiscoveryHypothesis).order_by(DiscoveryHypothesis.created_at.desc())).all()
    if not hyps:
        hyps = service.generate_hypotheses()
    return [{
        'id': h.id,
        'title': h.title,
        'industry': h.industry,
        'target_geography': h.target_geography,
        'target_service': h.target_service,
        'rationale': h.rationale,
        'status': h.status,
        'created_at': h.created_at.isoformat()
    } for h in hyps]

@router.post('/discovery/hypotheses/generate')
def generate_hypotheses(session: Session = Depends(get_db)):
    service = SearchService(session)
    hyps = service.generate_hypotheses()
    return {'generated_count': len(hyps)}

@router.get('/market/overview')
def market_overview(session: Session = Depends(get_db)):
    total_leads = session.scalar(select(func.count(Business.id))) or 0
    industries = session.execute(
        select(Business.industry, func.count(Business.id)).group_by(Business.industry)
    ).all()
    return {
        'total_discovered_leads': total_leads,
        'target_services': SPARKXFLOW_SERVICES,
        'target_geographies': TARGET_GEOGRAPHIES,
        'industry_distribution': [{'industry': ind or 'General', 'count': cnt} for ind, cnt in industries if cnt > 0]
    }

# --- Lead Extended Profile & Qualification ---

@router.get('/leads/{lead_id}/profile')
def get_lead_profile(lead_id: str, session: Session = Depends(get_db)):
    b = session.get(Business, lead_id)
    if not b: raise HTTPException(404, 'Lead not found')
    p = session.get(BusinessProfile, lead_id)
    return {
        'business_id': b.id,
        'name': b.name,
        'website': b.website,
        'domain': b.domain,
        'industry': b.industry,
        'location': b.location,
        'source': b.source,
        'sub_industry': p.sub_industry if p else '',
        'country': p.country if p else '',
        'city': p.city if p else b.location,
        'address': p.address if p else '',
        'phone': p.phone if p else '',
        'email': p.email if p else '',
        'social_profiles': json.loads(p.social_profiles) if p and p.social_profiles else {},
        'description': p.description if p else ''
    }

@router.put('/leads/{lead_id}/profile')
def update_lead_profile(lead_id: str, item: ProfileIn, session: Session = Depends(get_db)):
    b = session.get(Business, lead_id)
    if not b: raise HTTPException(404, 'Lead not found')
    p = session.get(BusinessProfile, lead_id)
    if not p:
        p = BusinessProfile(
            business_id=lead_id,
            sub_industry=item.sub_industry,
            country=item.country,
            city=item.city,
            address=item.address,
            phone=item.phone,
            email=item.email,
            description=item.description,
            updated_at=now()
        )
        session.add(p)
    else:
        p.sub_industry = item.sub_industry
        p.country = item.country
        p.city = item.city
        p.address = item.address
        p.phone = item.phone
        p.email = item.email
        p.description = item.description
        p.updated_at = now()
    session.commit()
    return {'status': 'updated'}

@router.get('/leads/{lead_id}/qualification')
def get_lead_qualification(lead_id: str, session: Session = Depends(get_db)):
    qual = session.scalars(
        select(LeadQualification).where(LeadQualification.business_id == lead_id).order_by(LeadQualification.created_at.desc())
    ).first()
    if not qual:
        return {'qualified': False, 'message': 'Lead has not been qualified yet'}
    return {
        'qualified': True,
        'id': qual.id,
        'business_id': qual.business_id,
        'business_quality_score': qual.business_quality_score,
        'conversion_potential_score': qual.conversion_potential_score,
        'evidence_confidence': qual.evidence_confidence,
        'service_scores': json.loads(qual.service_scores_json or '[]'),
        'missing_information': json.loads(qual.missing_information_json or '[]'),
        'ai_summary': qual.ai_summary,
        'created_at': qual.created_at.isoformat()
    }

# --- Engine C: Contact Intelligence ---

@router.get('/contacts')
def list_all_contacts(session: Session = Depends(get_db)):
    contacts = session.scalars(select(Contact).order_by(Contact.created_at.desc())).all()
    return [{
        'id': c.id,
        'business_id': c.business_id,
        'full_name': c.full_name,
        'job_title': c.job_title,
        'role_category': c.role_category,
        'email': c.email,
        'phone': c.phone,
        'linkedin_url': c.linkedin_url,
        'verification_status': c.verification_status,
        'confidence_level': c.confidence_level,
        'contact_source': c.contact_source,
        'manual_override': c.manual_override,
        'created_at': c.created_at.isoformat()
    } for c in contacts]

@router.get('/leads/{lead_id}/contacts')
def list_lead_contacts(lead_id: str, session: Session = Depends(get_db)):
    service = ContactService(session)
    contacts = service.get_contacts_for_business(lead_id)
    return [{
        'id': c.id,
        'business_id': c.business_id,
        'full_name': c.full_name,
        'job_title': c.job_title,
        'role_category': c.role_category,
        'email': c.email,
        'phone': c.phone,
        'linkedin_url': c.linkedin_url,
        'verification_status': c.verification_status,
        'confidence_level': c.confidence_level,
        'contact_source': c.contact_source,
        'manual_override': c.manual_override
    } for c in contacts]

@router.post('/leads/{lead_id}/contacts')
def add_lead_contact(lead_id: str, item: ContactIn, session: Session = Depends(get_db)):
    service = ContactService(session)
    c = service.create_or_update_contact(
        business_id=lead_id,
        full_name=item.full_name,
        job_title=item.job_title,
        role_category=item.role_category,
        email=item.email,
        phone=item.phone,
        linkedin_url=item.linkedin_url,
        contact_source='Manual entry',
        manual_override=True
    )
    return {'id': c.id, 'status': 'created'}

@router.post('/leads/{lead_id}/contacts/discover')
def discover_lead_contacts(lead_id: str, session: Session = Depends(get_db)):
    service = ContactService(session)
    contacts = service.discover_public_decision_makers(lead_id)
    return {'discovered_count': len(contacts)}

@router.post('/contacts/{contact_id}/verify')
def verify_contact_email(contact_id: str, session: Session = Depends(get_db)):
    service = ContactService(session)
    return service.verify_email(contact_id)

# --- Engine D: Outreach & Approval Center ---

@router.get('/campaigns')
def list_campaigns(session: Session = Depends(get_db)):
    campaigns = session.scalars(select(Campaign).order_by(Campaign.created_at.desc())).all()
    return [{
        'id': c.id,
        'name': c.name,
        'target_audience': c.target_audience,
        'selected_services': json.loads(c.selected_services or '[]'),
        'target_countries': json.loads(c.target_countries or '[]'),
        'target_industries': json.loads(c.target_industries or '[]'),
        'status': c.status,
        'created_at': c.created_at.isoformat()
    } for c in campaigns]

@router.post('/campaigns')
def create_campaign(item: CampaignIn, session: Session = Depends(get_db)):
    camp = Campaign(
        name=item.name,
        target_audience=item.target_audience,
        selected_services=json.dumps(item.selected_services),
        target_countries=json.dumps(item.target_countries),
        target_industries=json.dumps(item.target_industries),
        status='active',
        created_at=now()
    )
    session.add(camp)
    session.commit()
    return {'id': camp.id, 'name': camp.name, 'status': camp.status}

@router.post('/outreach/generate')
def generate_personalized_draft(item: DraftGenerateIn, session: Session = Depends(get_db)):
    b = session.get(Business, item.business_id)
    if not b: raise HTTPException(404, 'Business not found')

    contact_name = ''
    contact_title = ''
    recipient_email = ''
    if item.contact_id:
        c = session.get(Contact, item.contact_id)
        if c:
            contact_name = c.full_name
            contact_title = c.job_title
            recipient_email = c.email
    elif not recipient_email:
        # Check if business profile has an email or find first contact
        c = session.scalars(select(Contact).where(Contact.business_id == b.id)).first()
        if c:
            contact_name = c.full_name
            contact_title = c.job_title
            recipient_email = c.email
        else:
            p = session.get(BusinessProfile, b.id)
            if p and p.email:
                recipient_email = p.email

    evidence_list = []
    if b.report:
        try:
            parsed_rep = json.loads(b.report)
            evidence_list = parsed_rep.get('evidence', [])
        except Exception:
            pass

    draft = EmailPersonalizer.generate_draft(
        business_name=b.name,
        service_name=item.target_service,
        contact_name=contact_name,
        contact_title=contact_title,
        evidence_list=evidence_list,
        location=b.location
    )

    msg = OutreachMessage(
        campaign_id=item.campaign_id,
        business_id=b.id,
        contact_id=item.contact_id,
        recipient_email=recipient_email or f"contact@{b.domain or 'example.com'}",
        subject=draft['subject'],
        body_text=draft['body_text'],
        personalization_notes=draft['personalization_notes'],
        evidence_references=json.dumps(draft['evidence_references']),
        status='pending_approval',
        created_at=now(),
        updated_at=now()
    )
    session.add(msg)
    session.commit()
    return {
        'id': msg.id,
        'business_name': b.name,
        'recipient_email': msg.recipient_email,
        'subject': msg.subject,
        'body_text': msg.body_text,
        'status': msg.status,
        'personalization_notes': msg.personalization_notes
    }

@router.get('/outreach/messages')
def list_outreach_messages(status: Optional[str] = None, session: Session = Depends(get_db)):
    stmt = select(OutreachMessage, Business.name).join(Business, OutreachMessage.business_id == Business.id)
    if status:
        stmt = stmt.where(OutreachMessage.status == status)
    stmt = stmt.order_by(OutreachMessage.created_at.desc())
    results = session.execute(stmt).all()
    return [{
        'id': m.id,
        'business_id': m.business_id,
        'business_name': bname,
        'recipient_email': m.recipient_email,
        'subject': m.subject,
        'body_text': m.body_text,
        'status': m.status,
        'personalization_notes': m.personalization_notes,
        'approved_at': m.approved_at.isoformat() if m.approved_at else None,
        'sent_at': m.sent_at.isoformat() if m.sent_at else None,
        'error_reason': m.error_reason,
        'created_at': m.created_at.isoformat()
    } for m, bname in results]

@router.post('/outreach/messages/{message_id}/approve')
def approve_outreach_message(message_id: str, session: Session = Depends(get_db)):
    service = ApprovalService(session)
    msg = service.approve_message(message_id)
    return {'id': msg.id, 'status': msg.status, 'approved_at': msg.approved_at.isoformat()}

@router.post('/outreach/messages/{message_id}/reject')
def reject_outreach_message(message_id: str, reason: str = 'Rejected by reviewer', session: Session = Depends(get_db)):
    service = ApprovalService(session)
    msg = service.reject_message(message_id, reason)
    return {'id': msg.id, 'status': msg.status}

@router.put('/outreach/messages/{message_id}/edit')
def edit_outreach_message(message_id: str, item: MessageEditIn, session: Session = Depends(get_db)):
    service = ApprovalService(session)
    msg = service.edit_message(message_id, item.subject, item.body_text)
    return {'id': msg.id, 'status': msg.status, 'notice': 'Message updated. Previous approval revoked; requires re-approval.'}

@router.post('/outreach/messages/{message_id}/send')
def send_outreach_message(message_id: str, session: Session = Depends(get_db)):
    service = ApprovalService(session)
    result = service.execute_send(message_id)
    if result.get('success'):
        # Schedule follow-up cadence
        fu_service = FollowUpService(session)
        fu_service.schedule_cadence_for_message(message_id)
    return result

@router.get('/inbox')
def list_inbox_messages(session: Session = Depends(get_db)):
    messages = session.scalars(select(InboxMessage).order_by(InboxMessage.received_at.desc())).all()
    return [{
        'id': m.id,
        'sender': m.sender,
        'recipient': m.recipient,
        'subject': m.subject,
        'body': m.body,
        'classification': m.classification,
        'suggested_reply': m.suggested_reply,
        'received_at': m.received_at.isoformat()
    } for m in messages]

@router.post('/inbox/simulate-reply')
def simulate_inbound_reply(item: SimulateReplyIn, session: Session = Depends(get_db)):
    service = InboxService(session)
    msg = service.record_incoming_message(
        sender_email=item.sender_email,
        recipient_email=item.recipient_email,
        subject=item.subject,
        body=item.body,
        outreach_message_id=item.outreach_message_id
    )
    return {
        'id': msg.id,
        'classification': msg.classification,
        'suggested_reply': msg.suggested_reply
    }

@router.get('/follow-ups')
def list_followups(session: Session = Depends(get_db)):
    tasks = session.scalars(select(FollowUpTask).order_by(FollowUpTask.due_at.asc())).all()
    return [{
        'id': t.id,
        'business_id': t.business_id,
        'step_number': t.step_number,
        'due_at': t.due_at.isoformat(),
        'status': t.status,
        'cancellation_reason': t.cancellation_reason
    } for t in tasks]

@router.post('/follow-ups/{task_id}/approve')
def approve_followup_task(task_id: str, session: Session = Depends(get_db)):
    service = FollowUpService(session)
    task = service.approve_followup(task_id)
    return {'id': task.id, 'status': task.status}

@router.get('/suppression')
def list_suppression(session: Session = Depends(get_db)):
    entries = session.scalars(select(SuppressionEntry).order_by(SuppressionEntry.added_at.desc())).all()
    return [{
        'id': e.id,
        'email': e.email,
        'domain': e.domain,
        'reason': e.reason,
        'added_at': e.added_at.isoformat()
    } for e in entries]

@router.post('/suppression')
def add_suppression(email: str, reason: str = 'Manual addition', session: Session = Depends(get_db)):
    em = email.strip().lower()
    existing = session.scalars(select(SuppressionEntry).where(SuppressionEntry.email == em)).first()
    if not existing:
        entry = SuppressionEntry(email=em, reason=reason, added_at=now())
        session.add(entry)
        session.commit()
    return {'status': 'suppressed', 'email': em}

# --- Engine E: Sales Pipeline & Dashboard Overview ---

@router.get('/pipeline')
def list_pipeline(session: Session = Depends(get_db)):
    items = session.execute(
        select(SalesPipelineItem, Business.name, Business.website)
        .join(Business, SalesPipelineItem.business_id == Business.id)
        .order_by(SalesPipelineItem.updated_at.desc())
    ).all()
    return [{
        'id': p.id,
        'business_id': p.business_id,
        'business_name': bname,
        'website': bweb,
        'stage': p.stage,
        'deal_value': p.deal_value,
        'priority': p.priority,
        'assigned_service': p.assigned_service,
        'notes': p.notes,
        'updated_at': p.updated_at.isoformat()
    } for p, bname, bweb in items]

@router.put('/pipeline/{pipeline_id}')
def update_pipeline(pipeline_id: str, item: PipelineUpdateIn, session: Session = Depends(get_db)):
    p = session.get(SalesPipelineItem, pipeline_id)
    if not p: raise HTTPException(404, 'Pipeline deal not found')
    p.stage = item.stage
    p.deal_value = item.deal_value
    p.priority = item.priority
    p.notes = item.notes
    p.updated_at = now()
    session.commit()
    return {'status': 'updated'}

@router.post('/pipeline/bulk-stage')
def bulk_update_pipeline_stage(item: BulkStageIn, session: Session = Depends(get_db)):
    updated_count = 0
    for bid in item.business_ids:
        pipe = session.scalars(select(SalesPipelineItem).where(SalesPipelineItem.business_id == bid)).first()
        if not pipe:
            pipe = SalesPipelineItem(
                business_id=bid,
                stage=item.stage,
                notes=item.notes or '',
                created_at=now(),
                updated_at=now()
            )
            session.add(pipe)
            updated_count += 1
        else:
            pipe.stage = item.stage
            if item.notes:
                pipe.notes = f"{pipe.notes}\n{item.notes}".strip() if pipe.notes else item.notes
            pipe.updated_at = now()
            updated_count += 1
    session.commit()
    return {'success': True, 'updated_count': updated_count, 'new_stage': item.stage}

@router.post('/leads/bulk-tag')
def bulk_tag_leads(item: BulkTagIn, session: Session = Depends(get_db)):
    tag_clean = item.tag.strip()
    updated_count = 0
    for bid in item.business_ids:
        b = session.get(Business, bid)
        if b:
            p = session.get(BusinessProfile, bid)
            if not p:
                p = BusinessProfile(business_id=bid, description=f"Tag: {tag_clean}", updated_at=now())
                session.add(p)
            else:
                desc = p.description or ''
                if tag_clean.lower() not in desc.lower():
                    p.description = f"{desc} | Tag: {tag_clean}".strip(' |')
                    p.updated_at = now()
            updated_count += 1
    session.commit()
    return {'success': True, 'tagged_count': updated_count, 'tag': tag_clean}

@router.get('/dashboard/stats')
def get_dashboard_stats(session: Session = Depends(get_db)):
    total_leads = session.scalar(select(func.count(Business.id))) or 0
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = session.scalar(
        select(func.count(Business.id)).where(Business.created_at >= today_start)
    ) or 0
    qualified = session.scalar(select(func.count(LeadQualification.id))) or 0
    contacts_count = session.scalar(select(func.count(Contact.id))) or 0
    pending_approvals = session.scalar(
        select(func.count(OutreachMessage.id)).where(OutreachMessage.status == 'pending_approval')
    ) or 0
    emails_sent = session.scalar(
        select(func.count(OutreachMessage.id)).where(OutreachMessage.status == 'sent')
    ) or 0
    replies_count = session.scalar(
        select(func.count(InboxMessage.id)).where(InboxMessage.direction == 'inbound')
    ) or 0
    meetings_booked = session.scalar(
        select(func.count(InboxMessage.id)).where(InboxMessage.classification == 'meeting_interest')
    ) or 0
    conversion_rate = round((meetings_booked / emails_sent * 100), 1) if emails_sent > 0 else 0.0

    target_country = os.environ.get('TARGET_COUNTRY', 'US').strip().upper()
    is_india = target_country == 'IN'

    return {
        'total_discovered': total_leads,
        'new_leads_today': new_today,
        'qualified_leads': qualified,
        'high_priority_opportunities': min(qualified, total_leads),
        'contacts_discovered': contacts_count,
        'emails_awaiting_approval': pending_approvals,
        'emails_sent': emails_sent,
        'replies_received': replies_count,
        'meetings_booked': meetings_booked,
        'conversion_rate_pct': conversion_rate,
        'jobs_running': session.scalar(select(func.count(SearchJob.id)).where(SearchJob.status == 'running')) or 0,
        'failed_jobs': session.scalar(select(func.count(SearchJob.id)).where(SearchJob.status == 'failed')) or 0,
        'target_country': target_country,
        'default_country': 'India' if is_india else 'United States',
        'default_city': 'Bengaluru' if is_india else 'New York',
        'default_connector': 'osm_overpass' if is_india else 'public_directory'
    }

# --- Integrations & Automation Control ---

@router.get('/integrations')
def list_integrations(session: Session = Depends(get_db)):
    items = session.scalars(select(SystemIntegration)).all()
    results = []
    for i in items:
        cfg = json.loads(i.config_json or '{}')
        # Redact secrets from API responses to prevent secret leakage
        if i.service_name == 'google_sheets':
            sheets_service = GoogleSheetsSyncService(session)
            cfg = sheets_service.get_safe_config()
        elif 'webhook_secret' in cfg:
            has_secret = bool(cfg.get('webhook_secret'))
            cfg['has_secret'] = has_secret
            cfg['webhook_secret_masked'] = '••••••••' if has_secret else ''
            cfg.pop('webhook_secret', None)

        results.append({
            'id': i.id,
            'service_name': i.service_name,
            'is_enabled': i.is_enabled,
            'status': i.status,
            'config': cfg,
            'last_synced_at': i.last_synced_at.isoformat() if i.last_synced_at else None,
            'error_message': i.error_message
        })
    return results

@router.post('/integrations/google-sheets/sync')
def sync_google_sheets(session: Session = Depends(get_db)):
    service = GoogleSheetsSyncService(session)
    return service.sync_to_sheets()

@router.post('/integrations/google-sheets/config')
def configure_google_sheets(
    item: Optional[GoogleSheetsConfigIn] = None,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    is_enabled: bool = True,
    session: Session = Depends(get_db)
):
    service = GoogleSheetsSyncService(session)
    url = item.webhook_url if item and item.webhook_url is not None else (webhook_url or '')
    secret = item.webhook_secret if item and item.webhook_secret is not None else webhook_secret
    enabled = item.is_enabled if item is not None else is_enabled
    sheet_id = item.sheet_id if item and item.sheet_id else None

    try:
        integration = service.update_config(
            webhook_url=url,
            webhook_secret=secret,
            sheet_id=sheet_id,
            is_enabled=enabled
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    safe_cfg = service.get_safe_config()
    return {
        'status': 'configured' if url.strip() else 'unconfigured',
        'is_enabled': integration.is_enabled,
        'config': safe_cfg
    }

@router.post('/integrations/n8n/config')
def configure_n8n(item: N8nConfigIn, session: Session = Depends(get_db)):
    service = N8nAutomationService(session)
    integration = service.update_config(
        webhook_url=item.webhook_url,
        is_enabled=item.is_enabled,
        events=item.events
    )
    return {
        'status': integration.status,
        'is_enabled': integration.is_enabled,
        'service_name': 'n8n_automation'
    }

@router.post('/integrations/n8n/test')
def test_n8n_webhook(session: Session = Depends(get_db)):
    service = N8nAutomationService(session)
    return service.test_connection()

@router.post('/integrations/sending/toggle')
def toggle_email_sending(enabled: bool, session: Session = Depends(get_db)):
    item = session.scalars(select(SystemIntegration).where(SystemIntegration.service_name == 'email_sending')).first()
    if not item:
        item = SystemIntegration(
            service_name='email_sending',
            is_enabled=enabled,
            status='active' if enabled else 'disabled',
            created_at=now()
        )
        session.add(item)
    else:
        item.is_enabled = enabled
        item.status = 'active' if enabled else 'disabled'
    session.commit()
    return {'email_sending_enabled': item.is_enabled}

@router.get('/automations/control')
def get_automation_control(session: Session = Depends(get_db)):
    coord = AutomationCoordinator(session)
    return {'autonomous_enabled': coord.is_autonomous_enabled()}

@router.post('/automations/toggle')
def toggle_autonomous_control(enabled: bool, session: Session = Depends(get_db)):
    coord = AutomationCoordinator(session)
    active = coord.set_autonomous_state(enabled)
    return {'autonomous_enabled': active}

