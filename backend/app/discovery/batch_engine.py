"""OutLead-Inspired Batch Discovery Engine.
Orchestrates multi-city, multi-category bulk searches with batch processing,
durable state tracking, pause/resume/cancellation, duplicate & branch detection,
enrichment handoff, and CSV export.

Attribution: OutLead (MIT License, Copyright 2026 OutLead contributors).
"""
import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Business, BusinessDomain, BusinessProfile, BusinessRelationship, DuplicateReview,
    Contact, LeadQualification, ResearchHistory, SearchJob
)
from .connectors import BaseConnector, ConnectorNotConfiguredError, DiscoveredLead

logger = logging.getLogger('sparkxflow.discovery.batch')


def now():
    return datetime.now(timezone.utc)


def parse_multivalue_input(raw: Any) -> List[str]:
    """Parse comma/newline separated string or list into clean distinct non-empty strings."""
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        # Support both comma-separated and newline-separated
        items = re.split(r'[\r\n,]+', raw)
    else:
        items = [str(raw)]

    seen = set()
    cleaned = []
    for item in items:
        val = str(item).strip()
        if val and val.lower() not in seen:
            seen.add(val.lower())
            cleaned.append(val)
    return cleaned


def build_batch_queries(cities: List[str],
                        categories: List[str],
                        template: str = "{category} in {city}") -> List[Dict[str, Any]]:
    """Build the Cartesian cross-product of categories x cities as manageable batch sub-queries."""
    clean_cities = [c.strip() for c in cities if c.strip()] or ['Bengaluru']
    clean_cats = [c.strip() for c in categories if c.strip()] or ['Local Business']

    sub_queries = []
    batch_index = 1
    for cat in clean_cats:
        for city in clean_cities:
            query_str = template.format(category=cat, city=city)
            sub_queries.append({
                'batch_index': batch_index,
                'category': cat,
                'city': city,
                'query': query_str,
                'status': 'pending',  # 'pending', 'completed', 'failed', 'skipped'
                'results_count': 0,
                'added_count': 0,
                'duplicate_count': 0,
                'error': None
            })
            batch_index += 1

    return sub_queries


def normalize_company_name_key(name: str) -> str:
    """Normalize business name for duplicate detection by removing legal suffixes."""
    if not name:
        return ""
    n = name.strip().lower()
    suffixes = [
        r'\bprivate\s+limited\b', r'\bpvt\.?\s*ltd\.?\b', r'\blimited\b',
        r'\bltd\.?\b', r'\bllp\b', r'\bincorporated\b', r'\binc\.?\b',
        r'\bcorporation\b', r'\bcorp\.?\b', r'\bco\.\b', r'\bcompany\b',
        r'\benterprises\b', r'\bsolutions\b',
    ]
    for s in suffixes:
        n = re.sub(s, '', n, flags=re.IGNORECASE)
    n = re.sub(r'[^a-z0-9\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()


class OutLeadBatchEngine:
    """Batch executor for multi-city, multi-category discovery jobs."""

    def __init__(self, session: Session, insert_lead_fn: Optional[Callable] = None):
        self.session = session
        self.insert_lead_fn = insert_lead_fn

    def prepare_job_batches(self,
                             job: SearchJob,
                             raw_cities: Any,
                             raw_categories: Any) -> List[Dict[str, Any]]:
        """Parse inputs, configure batches on the job, and persist."""
        cities = parse_multivalue_input(raw_cities)
        categories = parse_multivalue_input(raw_categories)

        if not cities and job.city:
            cities = parse_multivalue_input(job.city)
        if not categories and job.category:
            categories = parse_multivalue_input(job.category)

        sub_queries = build_batch_queries(cities, categories)
        job.cities = ", ".join(cities)
        job.categories = ", ".join(categories)
        job.batch_status = 'pending'
        job.batch_params = json.dumps({
            'batches_total': len(sub_queries),
            'batches_completed': 0,
            'batches_failed': 0,
            'leads_discovered': 0,
            'leads_added': 0,
            'leads_duplicate': 0,
            'sub_queries': sub_queries
        })
        self.session.commit()
        return sub_queries

    def pause_job(self, job_id: str) -> Dict[str, Any]:
        """Signal job to pause processing between batches."""
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        job.batch_status = 'paused'
        job.updated_at = now()
        self.session.commit()
        return {'job_id': job_id, 'batch_status': 'paused', 'progress': job.progress}

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """Resume paused job execution."""
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        job.batch_status = 'running'
        job.updated_at = now()
        self.session.commit()
        return self.execute_batch_job(job_id)

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel remaining batches of a job."""
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        job.batch_status = 'cancelled'
        job.status = 'cancelled'
        job.updated_at = now()
        self.session.commit()
        return {'job_id': job_id, 'batch_status': 'cancelled', 'status': 'cancelled'}

    def execute_batch_job(self,
                          job_id: str,
                          connectors: Optional[List[BaseConnector]] = None,
                          limit_per_batch: int = 10) -> Dict[str, Any]:
        """Execute all pending batch sub-queries for the job."""
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Load existing batch state or prepare initial batches
        batch_meta: Dict[str, Any] = {}
        if job.batch_params:
            try:
                batch_meta = json.loads(job.batch_params)
            except Exception:
                batch_meta = {}

        sub_queries: List[Dict[str, Any]] = batch_meta.get('sub_queries') or []
        if not sub_queries:
            sub_queries = self.prepare_job_batches(job, job.cities or job.city, job.categories or job.category)
            batch_meta = json.loads(job.batch_params)

        job.status = 'running'
        job.batch_status = 'running'
        self.session.commit()

        if connectors is None:
            from .connectors import get_connector, CONNECTOR_REGISTRY
            conn_name = job.connector_name or 'all_available'
            if conn_name == 'all_available':
                connectors = [c for c in CONNECTOR_REGISTRY.values() if c.is_configured()]
            else:
                c = get_connector(conn_name)
                connectors = [c] if c else []

        if not connectors:
            err = f"No active connectors available for '{job.connector_name}'"
            job.status = 'failed'
            job.batch_status = 'failed'
            job.error_log = err
            self.session.commit()
            return {'job_id': job.id, 'status': 'failed', 'error': err}

        total_batches = len(sub_queries)
        completed_batches = batch_meta.get('batches_completed', 0)
        failed_batches = batch_meta.get('batches_failed', 0)
        total_added = batch_meta.get('leads_added', 0)
        total_dups = batch_meta.get('leads_duplicate', 0)
        total_discovered = batch_meta.get('leads_discovered', 0)

        for sq in sub_queries:
            # Check for pause / cancel signals
            self.session.refresh(job)
            if job.batch_status in ('paused', 'cancelled'):
                logger.info("Batch job %s received %s signal, stopping execution.", job.id, job.batch_status)
                break

            if sq.get('status') == 'completed':
                continue

            batch_idx = sq.get('batch_index', 1)
            target_city = sq.get('city')
            target_cat = sq.get('category')
            target_query = sq.get('query')

            batch_leads: List[DiscoveredLead] = []
            batch_err = None

            for conn in connectors:
                try:
                    leads = conn.search(
                        query=target_query,
                        country=job.country or 'India',
                        city=target_city,
                        industry=job.industry or target_cat,
                        category=target_cat,
                        limit=limit_per_batch
                    )
                    batch_leads.extend(leads)
                except ConnectorNotConfiguredError as cne:
                    batch_err = f"Connector {conn.name} unconfigured: {str(cne)}"
                except Exception as ce:
                    logger.warning("Batch %d connector %s error: %s", batch_idx, conn.name, ce)
                    batch_err = str(ce)

            # Process discovered leads into database
            b_added = 0
            b_dups = 0

            for lead in batch_leads:
                added, dup = self._persist_lead(job, lead)
                if added:
                    b_added += 1
                elif dup:
                    b_dups += 1

            total_discovered += len(batch_leads)
            total_added += b_added
            total_dups += b_dups

            sq['results_count'] = len(batch_leads)
            sq['added_count'] = b_added
            sq['duplicate_count'] = b_dups
            if batch_leads or not batch_err:
                sq['status'] = 'completed'
                completed_batches += 1
            else:
                sq['status'] = 'failed'
                sq['error'] = batch_err
                failed_batches += 1

            # Update job progress
            job.progress = int((completed_batches + failed_batches) / max(total_batches, 1) * 100)
            job.results_count = total_added
            batch_meta['batches_completed'] = completed_batches
            batch_meta['batches_failed'] = failed_batches
            batch_meta['leads_discovered'] = total_discovered
            batch_meta['leads_added'] = total_added
            batch_meta['leads_duplicate'] = total_dups
            batch_meta['sub_queries'] = sub_queries
            job.batch_params = json.dumps(batch_meta)
            job.updated_at = now()
            self.session.commit()

        # Final status calculation
        self.session.refresh(job)
        if job.batch_status == 'cancelled':
            job.status = 'cancelled'
        elif job.batch_status == 'paused':
            job.status = 'paused'
        elif completed_batches == total_batches:
            job.status = 'completed'
            job.batch_status = 'completed'
            job.progress = 100
        elif completed_batches > 0:
            job.status = 'partial_success'
            job.batch_status = 'completed'
            job.progress = 100
        else:
            job.status = 'failed'
            job.batch_status = 'failed'

        self.session.commit()

        return {
            'job_id': job.id,
            'status': job.status,
            'batch_status': job.batch_status,
            'batches_total': total_batches,
            'batches_completed': completed_batches,
            'batches_failed': failed_batches,
            'leads_discovered': total_discovered,
            'added': total_added,
            'leads_added': total_added,
            'duplicates_flagged_for_review': total_dups,
            'leads_duplicate': total_dups
        }

    def _persist_lead(self, job: SearchJob, lead: DiscoveredLead) -> Tuple[bool, bool]:
        """Safely deduplicate, preserve branches, extract contacts and run qualification."""
        clean_name = (lead.name or '').strip()
        if not clean_name:
            return False, False

        clean_domain = (lead.domain or '').strip().lower()
        clean_website = (lead.website or '').strip()
        if not clean_domain and clean_website:
            clean_domain = DiscoveredLead._extract_domain(clean_website)
        sql_domain = clean_domain if clean_domain else None

        loc = f"{lead.city or ''}, {lead.country or ''}".strip(', ')
        source_provenance = f"Bulk Discovery ({lead.source_name}): {lead.source_url or lead.connector_name}"

        # 1. Check existing records
        existing: Optional[Business] = None
        is_branch = False

        if sql_domain:
            existing = self.session.scalars(
                select(Business).where(Business.domain == sql_domain)
            ).first()
            if not existing:
                dom_row = self.session.scalars(
                    select(BusinessDomain).where(BusinessDomain.domain == sql_domain)
                ).first()
                if dom_row:
                    existing = self.session.get(Business, dom_row.business_id)

            # Branch detection: same domain but clearly different physical city / address
            if existing:
                existing_loc = (existing.location or '').lower()
                current_city = (lead.city or '').lower()
                if current_city and current_city not in existing_loc:
                    # Mark as a separate physical branch rather than merging
                    is_branch = True

        if not existing:
            # Check exact name & location
            if loc:
                existing = self.session.scalars(
                    select(Business).where(Business.name == clean_name, Business.location == loc)
                ).first()
            else:
                existing = self.session.scalars(
                    select(Business).where(Business.name == clean_name)
                ).first()

        if not existing and loc:
            # Check normalized name key & city location
            norm_key = normalize_company_name_key(clean_name)
            if norm_key:
                candidates = self.session.scalars(
                    select(Business).where(Business.location.like(f"%{lead.city or ''}%"))
                ).all()
                for c in candidates:
                    if normalize_company_name_key(c.name) == norm_key:
                        existing = c
                        break

        # If it's a separate branch, create new business record and link relationship
        business_id = None
        added = False
        duplicate = False

        if not existing or is_branch:
            # If domain already exists on another business (is_branch), set businesses.domain to None
            # to respect the legacy UNIQUE constraint on businesses.domain, while recording the domain link
            # in business_domains (which supports multiple branches sharing a domain).
            biz_domain = sql_domain if not is_branch else None

            b = Business(
                name=clean_name,
                website=clean_website,
                domain=biz_domain,
                industry=lead.industry or '',
                location=loc,
                source=source_provenance
            )
            self.session.add(b)
            self.session.flush()

            if sql_domain:
                self.session.add(BusinessDomain(business_id=b.id, domain=sql_domain))
                self.session.flush()

            business_id = b.id
            added = True

            if is_branch and existing:
                # Record branch relationship with audit trail
                rev = DuplicateReview(
                    incoming=json.dumps({'name': clean_name, 'location': loc, 'website': clean_website, 'source': source_provenance}),
                    matches=json.dumps([{'business_id': existing.id, 'name': existing.name, 'location': existing.location}]),
                    status='resolved'
                )
                self.session.add(rev)
                self.session.flush()

                self.session.add(BusinessRelationship(
                    subject_business_id=b.id,
                    related_business_id=existing.id,
                    relation='branch_of',
                    review_id=rev.id,
                    created_at=now()
                ))
                self.session.flush()
        else:
            business_id = existing.id
            duplicate = True

        # Save / update extended OutLead place fields in BusinessProfile
        if business_id:
            profile = self.session.get(BusinessProfile, business_id)
            meta = lead.raw_metadata or {}
            if not profile:
                profile = BusinessProfile(
                    business_id=business_id,
                    sub_industry=lead.sub_industry or '',
                    country=lead.country or '',
                    city=lead.city or '',
                    address=lead.address or '',
                    phone=lead.phone or '',
                    email=lead.email or '',
                    description=lead.description or '',
                    rating=meta.get('rating'),
                    review_count=meta.get('review_count'),
                    business_hours=meta.get('business_hours'),
                    price_level=meta.get('price_level'),
                    latitude=meta.get('latitude'),
                    longitude=meta.get('longitude'),
                    place_id=meta.get('place_id'),
                    maps_url=meta.get('maps_url') or lead.source_url,
                    updated_at=now()
                )
                self.session.add(profile)
            else:
                if lead.address and not profile.address:
                    profile.address = lead.address
                if lead.phone and not profile.phone:
                    profile.phone = lead.phone
                if meta.get('rating') is not None:
                    profile.rating = meta.get('rating')
                if meta.get('review_count') is not None:
                    profile.review_count = meta.get('review_count')
                if meta.get('business_hours'):
                    profile.business_hours = meta.get('business_hours')
                if meta.get('price_level'):
                    profile.price_level = meta.get('price_level')
                if meta.get('latitude') is not None:
                    profile.latitude = meta.get('latitude')
                if meta.get('longitude') is not None:
                    profile.longitude = meta.get('longitude')
                if meta.get('place_id'):
                    profile.place_id = meta.get('place_id')
                if meta.get('maps_url'):
                    profile.maps_url = meta.get('maps_url')
                profile.updated_at = now()

            # Autonomous enrichment handoff: crawl website, extract contacts, run qualification
            if job.is_autonomous and clean_website and added:
                self._run_autonomous_enrichment(business_id, clean_name, clean_website)

        return added, duplicate

    def _run_autonomous_enrichment(self, business_id: str, clean_name: str, clean_website: str):
        """Crawl website, extract observed contacts and compute 9-service qualification."""
        try:
            from ..crawl_client import run_crawl
            from ..research.qualification_engine import QualificationEngine
            import os

            # Release SQLite lock before subprocess execution
            self.session.commit()

            root_path = Path(__file__).resolve().parents[3]
            db_file = (root_path / 'sparkxflow.db').resolve()
            db_url = os.environ.get('DATABASE_URL') or f"sqlite:///{db_file}"

            final_url, html = run_crawl(clean_website, db_url)
            qual_data = QualificationEngine.analyze(final_url, html, business_name=clean_name)
            obs_contacts = QualificationEngine.extract_public_contacts(final_url, html, business_name=clean_name)

            if obs_contacts:
                try:
                    from ..contacts.contact_service import ContactService
                    ContactService(self.session).save_observed_contacts(business_id, obs_contacts)
                except Exception as ce:
                    logger.debug("Observed contacts exception for %s: %s", clean_website, ce)

            self.session.add(LeadQualification(
                business_id=business_id,
                business_quality_score=qual_data.get('business_quality') or 0,
                conversion_potential_score=qual_data.get('conversion_potential') or 0,
                evidence_confidence=qual_data.get('evidence_confidence') or 'medium',
                service_scores_json=json.dumps(qual_data.get('opportunities', [])),
                missing_information_json=json.dumps(qual_data.get('missing_information', [])),
                ai_summary=qual_data.get('ai_summary', ''),
                created_at=now()
            ))
            self.session.add(ResearchHistory(
                business_id=business_id,
                report=json.dumps(qual_data),
                collected_at=now(),
                kind='observed'
            ))
            b_obj = self.session.get(Business, business_id)
            if b_obj:
                b_obj.researched_at = now()
                b_obj.report = json.dumps(qual_data)

            self.session.commit()
        except Exception as e:
            logger.warning("Autonomous enrichment failed for %s (%s): %s", clean_name, clean_website, e)

    def export_job_csv(self, job_id: str) -> str:
        """Export leads discovered by this job to CSV format."""
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Query all businesses with this job's provenance or discovered in this session
        query = select(Business).where(Business.source.like(f"%{job.connector_name}%") | Business.source.like(f"%{job.name}%"))
        businesses = self.session.scalars(query).all()
        if not businesses:
            businesses = self.session.scalars(select(Business).order_by(Business.created_at.desc()).limit(job.results_count or 50)).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Business Name", "Official Website", "Domain", "Industry",
            "Location", "Address", "Phone", "Rating", "Review Count",
            "Business Hours", "Maps URL", "Quality Score", "Primary Contact Email",
            "Source Provenance", "Discovered At"
        ])

        for b in businesses:
            profile = self.session.get(BusinessProfile, b.id)
            qual = self.session.scalars(select(LeadQualification).where(LeadQualification.business_id == b.id)).first()
            primary_contact = self.session.scalars(select(Contact).where(Contact.business_id == b.id, Contact.email != '')).first()

            writer.writerow([
                b.id,
                b.name,
                b.website or '',
                b.domain or '',
                b.industry or '',
                b.location or '',
                profile.address if profile else '',
                profile.phone if profile else '',
                profile.rating if (profile and profile.rating is not None) else '',
                profile.review_count if (profile and profile.review_count is not None) else '',
                profile.business_hours if profile else '',
                profile.maps_url if profile else '',
                qual.business_quality_score if qual else '',
                primary_contact.email if primary_contact else '',
                b.source or '',
                b.created_at.isoformat() if b.created_at else ''
            ])

        return output.getvalue()
