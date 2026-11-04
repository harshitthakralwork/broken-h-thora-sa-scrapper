"""Search and Discovery Service for SparkXFlow Engine A & B.
Coordinates manual targeted discovery, autonomous hypotheses, deduplication, and candidate storage.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Business, BusinessProfile, BusinessDomain, SearchJob, DiscoveryHypothesis, SourceConnector, now, uid
from .connectors import get_connector, DiscoveredLead, ConnectorNotConfiguredError

logger = logging.getLogger('sparkxflow.search_service')

SPARKXFLOW_SERVICES = [
    "Website Development",
    "Web Application Development",
    "AI Automation",
    "E-commerce Development",
    "SaaS Development",
    "SEO and Digital Marketing",
    "Mobile Application Development",
    "CRM and Business Automation",
    "Video Editing"
]

TARGET_GEOGRAPHIES = [
    "India",
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Germany",
    "France",
    "Singapore"
]

INDIAN_METROS = {
    'bengaluru': {'name': 'Bengaluru', 'state': 'Karnataka', 'aliases': ['bangalore', 'bengaluru']},
    'mumbai': {'name': 'Mumbai', 'state': 'Maharashtra', 'aliases': ['mumbai', 'bombay']},
    'delhi': {'name': 'Delhi', 'state': 'Delhi NCR', 'aliases': ['delhi', 'new delhi', 'delhi ncr']},
    'hyderabad': {'name': 'Hyderabad', 'state': 'Telangana', 'aliases': ['hyderabad', 'secunderabad']},
    'pune': {'name': 'Pune', 'state': 'Maharashtra', 'aliases': ['pune', 'poona']},
    'chennai': {'name': 'Chennai', 'state': 'Tamil Nadu', 'aliases': ['chennai', 'madras']},
    'kolkata': {'name': 'Kolkata', 'state': 'West Bengal', 'aliases': ['kolkata', 'calcutta']},
    'ahmedabad': {'name': 'Ahmedabad', 'state': 'Gujarat', 'aliases': ['ahmedabad']},
    'gurugram': {'name': 'Gurugram', 'state': 'Haryana', 'aliases': ['gurgaon', 'gurugram']},
    'noida': {'name': 'Noida', 'state': 'Uttar Pradesh', 'aliases': ['noida', 'greater noida']},
    'jaipur': {'name': 'Jaipur', 'state': 'Rajasthan', 'aliases': ['jaipur']},
    'kochi': {'name': 'Kochi', 'state': 'Kerala', 'aliases': ['kochi', 'cochin']}
}

def resolve_indian_metro(city_query: str) -> Optional[Dict[str, str]]:
    if not city_query:
        return None
    cq = city_query.strip().lower()
    for key, data in INDIAN_METROS.items():
        if any(alias in cq for alias in data['aliases']):
            return data
    return None

def normalize_company_name_key(name: str) -> str:
    """Normalize business name for duplicate detection by removing legal entity suffixes and punctuation.
    Preserves original name in storage while detecting corporate variations."""
    if not name:
        return ""
    n = name.strip().lower()
    suffixes = [
        r'\bprivate\s+limited\b',
        r'\bpvt\.?\s*ltd\.?\b',
        r'\blimited\b',
        r'\bltd\.?\b',
        r'\bllp\b',
        r'\bincorporated\b',
        r'\binc\.?\b',
        r'\bcorporation\b',
        r'\bcorp\.?\b',
        r'\bco\.\b',
        r'\bcompany\b',
        r'\benterprises\b',
        r'\bsolutions\b',
    ]
    for s in suffixes:
        n = re.sub(s, '', n, flags=re.IGNORECASE)
    n = re.sub(r'[^a-z0-9\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

class SearchService:
    def __init__(self, session: Session, insert_lead_fn=None):
        self.session = session
        self.insert_lead_fn = insert_lead_fn

    def create_search_job(self,
                          name: str,
                          query: str = '',
                          country: str = 'India',
                          city: str = 'Bengaluru',
                          industry: str = '',
                          category: str = '',
                          target_service: str = '',
                          max_leads: int = 25,
                          is_autonomous: bool = False,
                          connector_name: str = 'all_available',
                          cities: Optional[Any] = None,
                          categories: Optional[Any] = None) -> SearchJob:
        country = (country or 'India').strip()
        city = (city or 'Bengaluru').strip()
        job = SearchJob(
            name=name or f"Search {industry or query or 'Commercial'} in {city or country}",
            query=query,
            country=country,
            city=city,
            industry=industry,
            category=category,
            target_service=target_service,
            max_leads=max_leads,
            status='pending',
            progress=0,
            results_count=0,
            is_autonomous=is_autonomous,
            connector_name=connector_name,
            created_at=now(),
            updated_at=now()
        )
        self.session.add(job)
        self.session.commit()

        # If explicit multi-city, multi-category or bulk parameters provided, initialize batches
        if cities is not None or categories is not None:
            from .batch_engine import OutLeadBatchEngine
            OutLeadBatchEngine(self.session).prepare_job_batches(job, cities, categories)

        return job

    def execute_search_job(self, job_id: str) -> Dict[str, Any]:
        job = self.session.get(SearchJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = 'running'
        job.progress = 10
        self.session.commit()

        # Resolve connectors to run (supporting single, comma-separated, or 'all_available')
        connectors_to_run: List[Any] = []
        clean_conn = (job.connector_name or '').strip().lower()

        if clean_conn in ('all_available', 'all', 'multi'):
            from .connectors import CONNECTOR_REGISTRY
            seen_ids = set()
            for c in CONNECTOR_REGISTRY.values():
                if id(c) not in seen_ids:
                    seen_ids.add(id(c))
                    if c.is_configured():
                        connectors_to_run.append(c)
        elif ',' in clean_conn:
            seen_ids = set()
            for part in clean_conn.split(','):
                c = get_connector(part.strip())
                if c and id(c) not in seen_ids:
                    seen_ids.add(id(c))
                    connectors_to_run.append(c)
        else:
            c = get_connector(clean_conn)
            if c:
                connectors_to_run.append(c)

        if not connectors_to_run:
            err_msg = f"Unknown discovery connector: '{job.connector_name}'"
            logger.error("Search job %s failed: %s", job_id, err_msg)
            job.status = 'failed'
            job.error_log = err_msg
            job.updated_at = now()
            self.session.commit()
            return {
                'job_id': job.id,
                'status': 'failed',
                'error': err_msg,
                'added': 0,
                'duplicates_flagged_for_review': 0,
                'total_discovered': 0,
                'per_provider_counts': {},
                'provider_errors': {clean_conn: err_msg}
            }

        # If job is configured with batch sub-queries or is an OutLead bulk job, execute via Batch Engine
        if job.batch_params or job.cities or job.categories or clean_conn == 'outlead_bulk_maps':
            from .batch_engine import OutLeadBatchEngine
            batch_eng = OutLeadBatchEngine(self.session, self.insert_lead_fn)
            return batch_eng.execute_batch_job(
                job.id, connectors=connectors_to_run, limit_per_batch=max(job.max_leads // 5, 5)
            )

        # Multi-provider query execution with partial-success tolerance
        discovered: List[DiscoveredLead] = []
        provider_counts: Dict[str, int] = {}
        provider_errors: Dict[str, str] = {}

        limit_per_provider = max(job.max_leads // len(connectors_to_run), 5) if len(connectors_to_run) > 1 else job.max_leads

        for connector in connectors_to_run:
            try:
                leads = connector.search(
                    query=job.query,
                    country=job.country,
                    city=job.city,
                    industry=job.industry,
                    category=job.category,
                    limit=limit_per_provider
                )
                provider_counts[connector.name] = len(leads)
                discovered.extend(leads)
                last_err = getattr(connector, 'last_error', None)
                if not leads and last_err:
                    provider_errors[connector.name] = last_err
            except ConnectorNotConfiguredError as e:
                provider_errors[connector.name] = f"Connector not configured: {str(e)}"
            except Exception as e:
                logger.warning("Connector %s failed in search job %s: %s", connector.name, job.id, str(e))
                provider_errors[connector.name] = str(e)

        job.progress = 50
        self.session.commit()

        # If single connector was requested and failed with ConnectorNotConfiguredError:
        if len(connectors_to_run) == 1 and not discovered and provider_errors:
            single_err = list(provider_errors.values())[0]
            if "not configured" in single_err.lower():
                job.status = 'failed'
                job.error_log = single_err
                job.updated_at = now()
                self.session.commit()
                return {
                    'job_id': job.id,
                    'status': 'unconfigured',
                    'error': single_err,
                    'added': 0,
                    'duplicates_flagged_for_review': 0,
                    'total_discovered': 0,
                    'per_provider_counts': provider_counts,
                    'provider_errors': provider_errors
                }

        # If all connectors encountered unhandled errors and zero leads returned:
        if not discovered and len(provider_errors) == len(connectors_to_run):
            err_summary = "; ".join(f"{k}: {v}" for k, v in provider_errors.items())
            job.status = 'failed'
            job.error_log = err_summary
            job.updated_at = now()
            self.session.commit()
            return {
                'job_id': job.id,
                'status': 'failed',
                'error': err_summary,
                'added': 0,
                'duplicates_flagged_for_review': 0,
                'total_discovered': 0,
                'per_provider_counts': provider_counts,
                'provider_errors': provider_errors
            }

        added_count = 0
        review_count = 0

        for lead in discovered:
            clean_name = (lead.name or '').strip()
            if not clean_name:
                continue

            clean_domain = (lead.domain or '').strip().lower()
            clean_website = (lead.website or '').strip()
            if not clean_domain and clean_website:
                clean_domain = DiscoveredLead._extract_domain(clean_website)
            # Store missing or empty domains strictly as SQL NULL (None)
            sql_domain = clean_domain if clean_domain else None

            loc = f"{lead.city or ''}, {lead.country or ''}".strip(', ')
            business_id = None

            source_provenance = (
                f"CSV Import: {lead.source_url or 'User Upload'}"
                if lead.connector_name == 'csv_file'
                else f"Autonomous Discovery ({lead.source_name}): {lead.source_url or lead.connector_name}"
            )

            if self.insert_lead_fn:
                class DummyLeadIn:
                    def __init__(self, name, website, industry, location, source):
                        self.name = name
                        self.website = website
                        self.industry = industry
                        self.location = location
                        self.source = source

                    def model_dump(self):
                        return {
                            'name': self.name,
                            'website': self.website,
                            'industry': self.industry,
                            'location': self.location,
                            'source': self.source
                        }

                in_obj = DummyLeadIn(
                    name=clean_name,
                    website=clean_website,
                    industry=lead.industry or '',
                    location=loc,
                    source=source_provenance
                )
                b, rev = self.insert_lead_fn(in_obj, self.session, source_kind='connector')
                if b:
                    business_id = b.id
                    added_count += 1
                elif rev:
                    review_count += 1
            else:
                existing = None
                # 1. Match by domain if an actual non-empty domain exists
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

                # 2. Match by exact business name AND location (never merge different physical businesses just because they lack a domain)
                if not existing:
                    if loc:
                        existing = self.session.scalars(
                            select(Business).where(Business.name == clean_name, Business.location == loc)
                        ).first()
                    else:
                        existing = self.session.scalars(
                            select(Business).where(Business.name == clean_name)
                        ).first()

                # 3. Match by normalized name AND location (catch Pvt Ltd vs Private Limited at same location)
                # Caution: do NOT merge different physical locations/branches!
                if not existing and loc:
                    norm_key = normalize_company_name_key(clean_name)
                    if norm_key:
                        city_loc = lead.city or loc
                        candidates = self.session.scalars(
                            select(Business).where(Business.location.like(f"%{city_loc}%"))
                        ).all()
                        for cand in candidates:
                            if normalize_company_name_key(cand.name) == norm_key:
                                existing = cand
                                break

                if not existing:
                    b = Business(
                        name=clean_name,
                        website=clean_website,
                        domain=sql_domain,  # Explicitly None if no domain
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
                    added_count += 1
                else:
                    business_id = existing.id
                    review_count += 1

            # Save or update BusinessProfile with extended fields
            if business_id:
                profile = self.session.get(BusinessProfile, business_id)
                if not profile:
                    profile = BusinessProfile(
                        business_id=business_id,
                        sub_industry=lead.sub_industry,
                        country=lead.country,
                        city=lead.city,
                        address=lead.address,
                        phone=lead.phone,
                        email=lead.email,
                        social_profiles=json.dumps(lead.social_profiles),
                        description=lead.description,
                        updated_at=now()
                    )
                    self.session.add(profile)
                else:
                    if lead.sub_industry: profile.sub_industry = lead.sub_industry
                    if lead.country: profile.country = lead.country
                    if lead.city: profile.city = lead.city
                    if lead.address: profile.address = lead.address
                    if lead.phone: profile.phone = lead.phone
                    if lead.email: profile.email = lead.email
                    if lead.social_profiles: profile.social_profiles = json.dumps(lead.social_profiles)
                    if lead.description: profile.description = lead.description
                    profile.updated_at = now()

                # Process raw metadata for public contacts, qualification, and OutLead place fields
                if lead.raw_metadata:
                    meta = lead.raw_metadata
                    if meta.get('rating') is not None: profile.rating = meta.get('rating')
                    if meta.get('review_count') is not None: profile.review_count = meta.get('review_count')
                    if meta.get('business_hours'): profile.business_hours = meta.get('business_hours')
                    if meta.get('price_level'): profile.price_level = meta.get('price_level')
                    if meta.get('latitude') is not None: profile.latitude = meta.get('latitude')
                    if meta.get('longitude') is not None: profile.longitude = meta.get('longitude')
                    if meta.get('place_id'): profile.place_id = meta.get('place_id')
                    if meta.get('maps_url'): profile.maps_url = meta.get('maps_url')

                    raw_contacts = lead.raw_metadata.get('contacts') or []
                    if raw_contacts:
                        try:
                            from ..contacts.contact_service import ContactService
                            ContactService(self.session).save_observed_contacts(business_id, raw_contacts)
                        except Exception as ce:
                            logger.debug("Failed saving observed contacts: %s", ce)

                    qual_data = lead.raw_metadata.get('qual_data')
                    if qual_data:
                        try:
                            from ..models import LeadQualification, ResearchHistory
                            existing_qual = self.session.scalars(
                                select(LeadQualification).where(LeadQualification.business_id == business_id)
                            ).first()
                            if not existing_qual:
                                self.session.add(LeadQualification(
                                    business_id=business_id,
                                    business_quality_score=qual_data.get('business_quality') or 0,
                                    conversion_potential_score=qual_data.get('conversion_potential') or 0,
                                    evidence_confidence=qual_data.get('evidence_confidence') or 'high',
                                    service_scores_json=json.dumps(qual_data.get('opportunities', [])),
                                    missing_information_json=json.dumps(qual_data.get('missing_information', [])),
                                    ai_summary=qual_data.get('ai_summary', ''),
                                    created_at=now()
                                ))
                            if lead.website:
                                self.session.add(ResearchHistory(
                                    business_id=business_id,
                                    report=json.dumps(qual_data),
                                    collected_at=now(),
                                    kind='observed'
                                ))
                        except Exception as qe:
                            logger.debug("Failed saving qualification data: %s", qe)

                # Autonomous Pipeline Step: If job is autonomous and business has a website,
                # automatically perform compliant crawl and qualification if not yet researched
                if job.is_autonomous and clean_website and not (lead.raw_metadata and lead.raw_metadata.get('qual_data')):
                    try:
                        from ..models import LeadQualification, ResearchHistory
                        has_qual = self.session.scalars(
                            select(LeadQualification).where(LeadQualification.business_id == business_id)
                        ).first()
                        if not has_qual:
                            from ..crawl_client import run_crawl
                            from ..research.qualification_engine import QualificationEngine
                            import os
                            from pathlib import Path

                            # Commit current transaction to release SQLite locks before launching worker process
                            self.session.commit()

                            db_url = os.environ.get('DATABASE_URL')
                            if not db_url or db_url.startswith('sqlite:///.'):
                                root_path = Path(__file__).resolve().parents[3]
                                db_file = (root_path / 'sparkxflow.db').resolve()
                                db_url = f"sqlite:///{db_file}"

                            final_url, html = run_crawl(clean_website, db_url)
                            qual_data = QualificationEngine.analyze(final_url, html, business_name=clean_name)
                            obs_contacts = QualificationEngine.extract_public_contacts(final_url, html, business_name=clean_name)

                            if obs_contacts:
                                try:
                                    from ..contacts.contact_service import ContactService
                                    ContactService(self.session).save_observed_contacts(business_id, obs_contacts)
                                except Exception as ce:
                                    logger.debug("Autonomous contacts save exception: %s", ce)

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
                            biz_rec = self.session.get(Business, business_id)
                            if biz_rec:
                                biz_rec.researched_at = now()
                                biz_rec.report = json.dumps(qual_data)
                    except Exception as auto_crawl_err:
                        logger.warning("Autonomous research crawl failed for %s: %s", clean_website, auto_crawl_err)

        job.progress = 100
        # Partial-success indicator: if some providers had errors but others succeeded
        if provider_errors and (added_count > 0 or review_count > 0 or discovered):
            job.status = 'partial_success'
        else:
            job.status = 'completed'

        # Store clean JSON log of per-provider counts and errors
        job.error_log = json.dumps({
            'per_provider_counts': provider_counts,
            'provider_errors': provider_errors
        }) if (provider_counts or provider_errors) else ''
        job.results_count = added_count + review_count
        job.updated_at = now()
        self.session.commit()

        return {
            'job_id': job.id,
            'status': job.status,
            'added': added_count,
            'duplicates_flagged_for_review': review_count,
            'total_discovered': len(discovered),
            'per_provider_counts': provider_counts,
            'provider_errors': provider_errors
        }

    def generate_hypotheses(self) -> List[DiscoveryHypothesis]:
        """Engine A: Generate high-value market discovery hypotheses based on SparkXFlow services."""
        hypotheses_definitions = [
            ("Legacy Manufacturing & Logistics in UK/Midlands", "Supply Chain & Logistics", "United Kingdom", "AI Automation",
             "Logistics brokers operating with manual spreadsheet dispatched fleets have immediate 30%+ labor efficiency gain with automated order intake and route scheduling."),
            ("Independent Dental & Orthodontic Practices in US/Texas", "Healthcare & Medical", "United States", "CRM and Business Automation",
             "Multi-provider clinical practices running fragmented legacy scheduling software lose 15-20% of patient follow-ups and need modern intake automation."),
            ("High-End Boutique Fashion Retailers in Australia", "E-commerce & Retail", "Australia", "E-commerce Development",
             "Retailers with brick-and-mortar presence transitioning to digital DTC storefronts require optimized Shopify/custom headless checkout experiences."),
            ("B2B Corporate Law & Compliance Advisory in Canada", "Legal & Financial", "Canada", "Website Development",
             "Reputable partner-led advisory firms with non-responsive, 10-year-old static sites suffer high bounce rates when pitched to tech and enterprise clients."),
            ("Field Inspection & Maintenance Contractors in Germany", "Real Estate & Construction", "Germany", "Mobile Application Development",
             "Industrial contractors relying on paper inspection sheets and offline reporting require robust, cross-platform mobile utilities for on-site engineers."),
            ("Fast-Growing D2C Food & Beverage Brands in India", "Consumer Goods", "India", "SEO and Digital Marketing",
             "Emerging culinary brands with competitive offline shelf placement lack organic non-branded search dominance and structured schema markup."),
            ("Niche B2B SaaS Founders Seeking Micro-Video Explainers", "Technology & IT Services", "United States", "Video Editing",
             "Early-stage software companies with complex value propositions require high-converting product walkthroughs and motion-graphic social snippets."),
            ("Regional Accounting & Tax Practitioners in UK", "Financial Services", "United Kingdom", "Web Application Development",
             "Firms during peak fiscal periods need secure client document upload portals to replace insecure email attachments.")
        ]

        created = []
        for title, ind, geo, svc, rat in hypotheses_definitions:
            existing = self.session.scalars(
                select(DiscoveryHypothesis).where(DiscoveryHypothesis.title == title)
            ).first()
            if not existing:
                hyp = DiscoveryHypothesis(
                    title=title,
                    industry=ind,
                    target_geography=geo,
                    target_service=svc,
                    rationale=rat,
                    status='active',
                    created_at=now()
                )
                self.session.add(hyp)
                created.append(hyp)

        if created:
            self.session.commit()
        return created

    def pause_search_job(self, job_id: str) -> Dict[str, Any]:
        from .batch_engine import OutLeadBatchEngine
        return OutLeadBatchEngine(self.session).pause_job(job_id)

    def resume_search_job(self, job_id: str) -> Dict[str, Any]:
        from .batch_engine import OutLeadBatchEngine
        return OutLeadBatchEngine(self.session, self.insert_lead_fn).resume_job(job_id)

    def cancel_search_job(self, job_id: str) -> Dict[str, Any]:
        from .batch_engine import OutLeadBatchEngine
        return OutLeadBatchEngine(self.session).cancel_job(job_id)

    def export_search_job_csv(self, job_id: str) -> str:
        from .batch_engine import OutLeadBatchEngine
        return OutLeadBatchEngine(self.session).export_job_csv(job_id)

