"""Database models for SparkXFlow Lead Intelligence Engine.
Preserves all baseline models and adds extended intelligence tables.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def now():
    return datetime.now(timezone.utc)

def uid():
    return str(uuid.uuid4())

class Base(DeclarativeBase):
    pass

class Business(Base):
    __tablename__ = 'businesses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(2048), default='')
    domain: Mapped[Optional[str]] = mapped_column(String(253), unique=True, nullable=True)
    industry: Mapped[str] = mapped_column(String(120), default='')
    location: Mapped[str] = mapped_column(String(200), default='')
    source: Mapped[str] = mapped_column(String(2048), default='Manual import')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    report: Mapped[str] = mapped_column(Text, default='')
    researched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class DuplicateReview(Base):
    __tablename__ = 'duplicate_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incoming: Mapped[str] = mapped_column(Text)
    matches: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class ResearchHistory(Base):
    __tablename__ = 'research_history'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'), index=True)
    report: Mapped[str] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    kind: Mapped[str] = mapped_column(String(20), default='observed')

class IdentityGuard(Base):
    __tablename__ = 'identity_guard'
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    counter: Mapped[int] = mapped_column(Integer, default=0)

class BusinessDomain(Base):
    __tablename__ = 'business_domains'
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'), primary_key=True)
    domain: Mapped[str] = mapped_column(String(253), index=True)

class ImportBatch(Base):
    __tablename__ = 'import_batches'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    original_csv: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ImportCandidate(Base):
    __tablename__ = 'import_candidates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey('import_batches.id'))
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    business_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('businesses.id'), nullable=True)
    review_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('duplicate_reviews.id'), nullable=True)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class BusinessSource(Base):
    __tablename__ = 'business_sources'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    source: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[str] = mapped_column(String(32))
    candidate_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('import_candidates.id'), nullable=True)
    review_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('duplicate_reviews.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class BusinessRelationship(Base):
    __tablename__ = 'business_relationships'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject_business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    related_business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    relation: Mapped[str] = mapped_column(String(32))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey('duplicate_reviews.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ReviewResolution(Base):
    __tablename__ = 'review_resolutions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey('duplicate_reviews.id'))
    decision: Mapped[str] = mapped_column(String(32))
    matched_business_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('businesses.id'), nullable=True)
    result_business_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('businesses.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class CrawlerControl(Base):
    __tablename__ = 'crawler_control'
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    counter: Mapped[int] = mapped_column(Integer, default=0)

class CrawlerLease(Base):
    __tablename__ = 'crawler_leases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[float] = mapped_column(Float)

class CrawlerHostLimit(Base):
    __tablename__ = 'crawler_host_limits'
    host: Mapped[str] = mapped_column(String(253), primary_key=True)
    next_allowed: Mapped[float] = mapped_column(Float)
    owner: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    active_until: Mapped[float] = mapped_column(Float, default=0.0)

# Intelligence Platform Extensions
class BusinessProfile(Base):
    __tablename__ = 'business_profiles'
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'), primary_key=True)
    sub_industry: Mapped[str] = mapped_column(String(120), default='')
    country: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    address: Mapped[str] = mapped_column(String(500), default='')
    phone: Mapped[str] = mapped_column(String(100), default='')
    email: Mapped[str] = mapped_column(String(255), default='')
    social_profiles: Mapped[str] = mapped_column(Text, default='{}')
    description: Mapped[str] = mapped_column(Text, default='')
    # OutLead-inspired place & review enrichment fields
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    business_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    place_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    maps_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SearchJob(Base):
    __tablename__ = 'search_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255))
    query: Mapped[str] = mapped_column(String(255), default='')
    country: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    industry: Mapped[str] = mapped_column(String(120), default='')
    category: Mapped[str] = mapped_column(String(120), default='')
    target_service: Mapped[str] = mapped_column(String(120), default='')
    max_leads: Mapped[int] = mapped_column(Integer, default=25)
    status: Mapped[str] = mapped_column(String(32), default='pending')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    is_autonomous: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_interval: Mapped[str] = mapped_column(String(50), default='manual')
    connector_name: Mapped[str] = mapped_column(String(100), default='general_directory')
    error_log: Mapped[str] = mapped_column(Text, default='')
    # OutLead-inspired batch processing metadata
    cities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    batch_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    batch_status: Mapped[Optional[str]] = mapped_column(String(32), default='pending', nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DiscoveryHypothesis(Base):
    __tablename__ = 'discovery_hypotheses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str] = mapped_column(String(120))
    target_geography: Mapped[str] = mapped_column(String(100))
    target_service: Mapped[str] = mapped_column(String(120))
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SourceConnector(Base):
    __tablename__ = 'source_connectors'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    connector_type: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=30)
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LeadQualification(Base):
    __tablename__ = 'lead_qualifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    business_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    conversion_potential_score: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[str] = mapped_column(String(20), default='low')
    service_scores_json: Mapped[str] = mapped_column(Text, default='{}')
    missing_information_json: Mapped[str] = mapped_column(Text, default='[]')
    ai_summary: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Contact(Base):
    __tablename__ = 'contacts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    full_name: Mapped[str] = mapped_column(String(200))
    job_title: Mapped[str] = mapped_column(String(200), default='')
    role_category: Mapped[str] = mapped_column(String(50), default='other')
    email: Mapped[str] = mapped_column(String(255), default='')
    phone: Mapped[str] = mapped_column(String(100), default='')
    linkedin_url: Mapped[str] = mapped_column(String(2048), default='')
    verification_status: Mapped[str] = mapped_column(String(32), default='unknown')
    confidence_level: Mapped[str] = mapped_column(String(20), default='low')
    contact_source: Mapped[str] = mapped_column(String(1000), default='Public web discovery')
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Campaign(Base):
    __tablename__ = 'campaigns'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255))
    target_audience: Mapped[str] = mapped_column(String(255), default='')
    selected_services: Mapped[str] = mapped_column(Text, default='[]')
    target_countries: Mapped[str] = mapped_column(Text, default='[]')
    target_industries: Mapped[str] = mapped_column(Text, default='[]')
    status: Mapped[str] = mapped_column(String(32), default='draft')
    sending_config: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class OutreachMessage(Base):
    __tablename__ = 'outreach_messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('campaigns.id'), nullable=True)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    contact_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('contacts.id'), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    body_text: Mapped[str] = mapped_column(Text)
    personalization_notes: Mapped[str] = mapped_column(Text, default='')
    evidence_references: Mapped[str] = mapped_column(Text, default='[]')
    status: Mapped[str] = mapped_column(String(32), default='pending_approval')
    approval_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class InboxMessage(Base):
    __tablename__ = 'inbox_messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    outreach_message_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('outreach_messages.id'), nullable=True)
    business_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('businesses.id'), nullable=True)
    contact_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('contacts.id'), nullable=True)
    direction: Mapped[str] = mapped_column(String(20), default='inbound')
    sender: Mapped[str] = mapped_column(String(255))
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(50), default='neutral')
    suggested_reply: Mapped[str] = mapped_column(Text, default='')
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FollowUpTask(Base):
    __tablename__ = 'follow_up_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('campaigns.id'), nullable=True)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    contact_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('contacts.id'), nullable=True)
    step_number: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(32), default='scheduled')
    cancellation_reason: Mapped[str] = mapped_column(String(255), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SuppressionEntry(Base):
    __tablename__ = 'suppression_list'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(253), default='')
    reason: Mapped[str] = mapped_column(String(100), default='unsubscribed')
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SalesPipelineItem(Base):
    __tablename__ = 'sales_pipeline'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey('businesses.id'))
    stage: Mapped[str] = mapped_column(String(50), default='discovered')
    deal_value: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(20), default='medium')
    assigned_service: Mapped[str] = mapped_column(String(120), default='Website Development')
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SystemIntegration(Base):
    __tablename__ = 'system_integrations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_name: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default='disconnected')
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AutomationJob(Base):
    __tablename__ = 'automation_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    schedule_cron: Mapped[str] = mapped_column(String(100), default='0 9 * * *')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(32), default='pending')
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

