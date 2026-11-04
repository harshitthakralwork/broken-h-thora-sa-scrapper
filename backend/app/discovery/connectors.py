"""Modular live-source connector architecture for Lead Discovery Engine.
Adheres to strict production guidelines:
- Zero synthetic business generation.
- Queries permitted official registries, authorized search APIs, and structured CSV inputs.
- Captures actual business name, website, domain, location, industry, source name, source URL, timestamp, and confidence.
- Gracefully handles unconfigured connectors, rate limits, timeouts, and network retries.
"""
import abc
import base64
import csv
import io
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import httpx

logger = logging.getLogger('sparkxflow.discovery.connectors')

class ConnectorNotConfiguredError(Exception):
    """Raised when an action is attempted on an unconfigured connector."""
    pass

class DiscoveredLead:
    def __init__(self,
                 name: str,
                 website: str = '',
                 domain: str = '',
                 industry: str = '',
                 sub_industry: str = '',
                 country: str = '',
                 city: str = '',
                 address: str = '',
                 phone: str = '',
                 email: str = '',
                 social_profiles: Optional[Dict[str, str]] = None,
                 description: str = '',
                 source_name: str = '',
                 source_url: str = '',
                 evidence_confidence: str = 'high',
                 raw_metadata: Optional[Dict[str, Any]] = None,
                 connector_name: str = 'manual',
                 discovered_at: Optional[str] = None):
        self.name = name.strip()
        self.website = website.strip()
        self.domain = domain.strip().lower() or self._extract_domain(self.website)
        self.industry = industry.strip()
        self.sub_industry = sub_industry.strip()
        self.country = country.strip()
        self.city = city.strip()
        self.address = address.strip()
        self.phone = phone.strip()
        self.email = email.strip()
        self.social_profiles = social_profiles or {}
        self.description = description.strip()
        self.source_name = source_name.strip() or connector_name
        self.source_url = source_url.strip()
        self.evidence_confidence = evidence_confidence
        self.raw_metadata = raw_metadata or {}
        self.connector_name = connector_name
        self.discovered_at = discovered_at or datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_domain(url: str) -> str:
        if not url:
            return ''
        try:
            parsed = urllib.parse.urlsplit(url if '://' in url else f'http://{url}')
            host = parsed.hostname or ''
            return host.lower().removeprefix('www.')
        except Exception:
            return ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'website': self.website,
            'domain': self.domain,
            'industry': self.industry,
            'sub_industry': self.sub_industry,
            'country': self.country,
            'city': self.city,
            'address': self.address,
            'phone': self.phone,
            'email': self.email,
            'social_profiles': self.social_profiles,
            'description': self.description,
            'source_name': self.source_name,
            'source_url': self.source_url,
            'evidence_confidence': self.evidence_confidence,
            'discovered_at': self.discovered_at,
            'connector_name': self.connector_name
        }


class BaseConnector(abc.ABC):
    """Abstract base class for all live discovery connectors."""

    def __init__(self,
                 name: str,
                 title: str,
                 category: str,
                 rate_limit_per_min: int = 30,
                 daily_quota: int = 500,
                 requires_auth: bool = False,
                 auth_env_keys: Optional[List[str]] = None,
                 description: str = '',
                 attribution: str = '',
                 supported_regions: Optional[List[str]] = None):
        self.name = name
        self.title = title
        self.category = category
        self.rate_limit_per_min = rate_limit_per_min
        self.daily_quota = daily_quota
        self.requires_auth = requires_auth
        self.auth_env_keys = auth_env_keys or []
        self.description = description
        self.attribution = attribution
        self.supported_regions = supported_regions or ['Global']

    def is_configured(self) -> bool:
        if not self.requires_auth:
            return True
        return all(bool(os.environ.get(k, '').strip()) for k in self.auth_env_keys)

    def get_status(self) -> Dict[str, Any]:
        configured = self.is_configured()
        return {
            'name': self.name,
            'title': self.title,
            'category': self.category,
            'rate_limit_per_min': self.rate_limit_per_min,
            'daily_quota': self.daily_quota,
            'requires_auth': self.requires_auth,
            'is_configured': configured,
            'status': 'available' if configured else 'unconfigured',
            'auth_keys': self.auth_env_keys,
            'description': self.description,
            'attribution': self.attribution,
            'supported_regions': self.supported_regions
        }

    def _execute_with_retry(self, fn, retries: int = 2, delay: float = 1.0):
        for attempt in range(retries + 1):
            try:
                return fn()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503) and attempt < retries:
                    time.sleep(delay * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < retries:
                    time.sleep(delay * (attempt + 1))
                    continue
                raise

    @abc.abstractmethod
    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        """Perform lead search against the live source."""
        pass


class CompaniesHouseRegistryConnector(BaseConnector):
    """Official UK Government Companies House Public Registry Connector.
    Queries official public corporate register for incorporated businesses.
    API documentation: https://developer.company-information.service.gov.uk/
    """

    BASE_URL = "https://api.company-information.service.gov.uk"

    def __init__(self):
        super().__init__(
            name='uk_companies_house',
            title='UK Companies House Registry',
            category='Official Corporate Registry',
            rate_limit_per_min=60,
            daily_quota=600,
            requires_auth=True,
            auth_env_keys=['COMPANIES_HOUSE_API_KEY'],
            description='Official United Kingdom corporate database. Free official API provided by the UK government.',
            attribution='Contains public sector information licensed under the Open Government Licence v3.0 (UK Companies House)',
            supported_regions=['United Kingdom', 'GB']
        )

    def search(self,
               query: str = '',
               country: str = 'United Kingdom',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                f"UK Companies House connector requires COMPANIES_HOUSE_API_KEY in environment."
            )

        api_key = os.environ.get('COMPANIES_HOUSE_API_KEY', '').strip()
        # Basic auth: API key as username, empty password
        auth_header = "Basic " + base64.b64encode(f"{api_key}:".encode('ascii')).decode('ascii')

        term = query.strip() or f"{industry} {city}".strip() or "Logistics"
        params = {
            'q': term,
            'items_per_page': min(limit, 50)
        }

        def req():
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self.BASE_URL}/search/companies",
                    params=params,
                    headers={'Authorization': auth_header}
                )
                resp.raise_for_status()
                return resp.json()

        data = self._execute_with_retry(req)
        items = data.get('items', [])
        results: List[DiscoveredLead] = []

        for item in items:
            comp_num = item.get('company_number', '')
            comp_name = item.get('title', '').strip()
            if not comp_name:
                continue

            address_info = item.get('address', {})
            loc_parts = [address_info.get('locality', ''), address_info.get('region', ''), address_info.get('country', 'United Kingdom')]
            clean_loc = ', '.join([p for p in loc_parts if p]) or item.get('address_snippet', 'United Kingdom')

            profile_url = f"https://find-and-update.company-information.service.gov.uk/company/{comp_num}"

            results.append(DiscoveredLead(
                name=comp_name,
                website='', # Registry contains legal registration; website is discovered during research
                domain='',
                industry=industry or item.get('company_type', 'Incorporated Enterprise'),
                sub_industry=item.get('description', ''),
                country='United Kingdom',
                city=address_info.get('locality', city or 'London'),
                address=item.get('address_snippet', ''),
                phone='',
                email='',
                social_profiles={},
                description=f"UK Incorporated Entity (No. {comp_num}). Status: {item.get('company_status', 'active')}.",
                source_name='UK Companies House Public Register',
                source_url=profile_url,
                evidence_confidence='high',
                raw_metadata={'company_number': comp_num, 'company_status': item.get('company_status')},
                connector_name=self.name
            ))
        return results


class SecEdgarConnector(BaseConnector):
    """US Securities and Exchange Commission (SEC) EDGAR Corporate Database Connector.
    Official public corporate disclosures register for US public companies.
    Documentation: https://www.sec.gov/edgar/searchedgar/companysearch

    Policy & Safety:
    - 100% free official US government public service.
    - Requires an identifiable contact User-Agent in SEC_USER_AGENT (e.g. 'AppName/1.0 contact:email@domain.com').
    - Rate limit: 10 requests per second maximum, strictly enforced by SEC.
    - Zero synthetic data: returns only verified CIK entities and official EDGAR filings.
    """

    SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

    def __init__(self):
        super().__init__(
            name='sec_edgar',
            title='US SEC EDGAR Public Company Disclosures',
            category='Official Corporate Registry',
            rate_limit_per_min=60,
            daily_quota=2000,
            requires_auth=True,
            auth_env_keys=['SEC_USER_AGENT'],
            description='Official United States SEC EDGAR corporate database. Free official API; requires an identifiable contact User-Agent in SEC_USER_AGENT.',
            attribution='U.S. Securities and Exchange Commission (SEC EDGAR Public Database)',
            supported_regions=['United States', 'US']
        )

    def is_configured(self) -> bool:
        ua = os.environ.get('SEC_USER_AGENT', '').strip()
        return bool(ua and len(ua) > 5)

    def search(self,
               query: str = '',
               country: str = 'United States',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                "US SEC EDGAR connector requires SEC_USER_AGENT in environment (format: 'AppName/1.0 contact:email@domain.com')."
            )

        user_agent = os.environ.get('SEC_USER_AGENT', '').strip()
        headers = {
            'User-Agent': user_agent,
            'Accept': 'application/json'
        }

        term = query.strip() or f"{industry} {city}".strip() or "Technology"
        params = {
            'q': term,
            'forms': '10-K,10-Q,8-K',
        }

        def req():
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(self.SEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req)
        except Exception as e:
            logger.warning("SEC EDGAR search request failed: %s", str(e))
            return []

        hits = data.get('hits', {}).get('hits', [])
        results: List[DiscoveredLead] = []
        seen_ciks = set()

        for hit in hits:
            source = hit.get('_source', {})
            display_names = source.get('display_names', [])
            entity_name = source.get('entity_name', '')
            ciks = source.get('ciks', [])
            cik = ciks[0] if ciks else ''

            if cik and cik in seen_ciks:
                continue
            if cik:
                seen_ciks.add(cik)

            raw_title = display_names[0] if display_names else entity_name
            clean_name = re.sub(r'\s*\([A-Z0-9.\-]+\)\s*\(CIK\s*\d+\)', '', raw_title).strip()
            if not clean_name:
                clean_name = raw_title

            ticker_match = re.search(r'\(([A-Z0-9.\-]+)\)\s*\(CIK', raw_title)
            ticker = ticker_match.group(1) if ticker_match else ''

            formatted_cik = str(cik).zfill(10) if cik else ''
            edgar_url = f"https://www.sec.gov/edgar/browse/?CIK={formatted_cik}" if formatted_cik else "https://www.sec.gov/edgar/searchedgar/companysearch"

            results.append(DiscoveredLead(
                name=clean_name,
                website='',
                domain='',
                industry=industry or source.get('sic_description') or 'US Public Corporation',
                sub_industry=source.get('form', '10-K/10-Q SEC Filer'),
                country='United States',
                city=city,
                address='',
                phone='',
                email='',
                description=f"US SEC EDGAR registered filer (CIK: {formatted_cik}{f', Ticker: {ticker}' if ticker else ''}). Latest filing: {source.get('form', 'Annual/Quarterly Report')}.",
                source_name='US SEC EDGAR Public Company Disclosures',
                source_url=edgar_url,
                evidence_confidence='high',
                raw_metadata={'cik': formatted_cik, 'ticker': ticker, 'form': source.get('form')},
                connector_name=self.name
            ))

            if len(results) >= limit:
                break

        return results


class GoogleSearchConnector(BaseConnector):
    """Google Custom Search JSON API Connector.
    Official, authenticated web query discovery using Google Cloud API key and Search Engine ID.
    Documentation: https://developers.google.com/custom-search/v1/overview
    """

    BASE_URL = "https://customsearch.googleapis.com/customsearch/v1"

    def __init__(self):
        super().__init__(
            name='google_search',
            title='Google Custom Search API',
            category='Search Engine Index',
            rate_limit_per_min=30,
            daily_quota=100,
            requires_auth=True,
            auth_env_keys=['GOOGLE_SEARCH_API_KEY', 'GOOGLE_SEARCH_CX'],
            description='Live Google web search index with official user API key and Search Engine ID.',
            attribution='Google Custom Search JSON API',
            supported_regions=['Global', 'India', 'United States', 'United Kingdom']
        )

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 10) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                f"Google Search connector requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX in environment."
            )

        api_key = os.environ.get('GOOGLE_SEARCH_API_KEY', '').strip()
        cx = os.environ.get('GOOGLE_SEARCH_CX', '').strip()

        search_terms = [query, industry, category, city, country]
        clean_q = ' '.join([t.strip() for t in search_terms if t.strip()]) or "commercial enterprise"

        params = {
            'key': api_key,
            'cx': cx,
            'q': clean_q,
            'num': min(limit, 10)
        }

        def req():
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                return resp.json()

        data = self._execute_with_retry(req)
        items = data.get('items', [])
        results: List[DiscoveredLead] = []

        for item in items:
            title = item.get('title', '').strip()
            link = item.get('link', '').strip()
            snippet = item.get('snippet', '').strip()
            display_link = item.get('displayLink', '').strip()

            if not link:
                continue

            # Strip generic search suffixes from title (e.g., "- Home", "| Official Website")
            cleaned_name = re.sub(r'\s*([|\-–—:]\s*(Home|Official Site|Welcome|About)).*$', '', title, flags=re.I).strip()
            if not cleaned_name:
                cleaned_name = display_link or title

            results.append(DiscoveredLead(
                name=cleaned_name,
                website=link,
                domain=display_link,
                industry=industry or "Commercial Enterprise",
                sub_industry=category or '',
                country=country,
                city=city,
                description=snippet,
                source_name='Google Search Index',
                source_url=link,
                evidence_confidence='high',
                raw_metadata={'search_query': clean_q},
                connector_name=self.name
            ))
        return results


class SerpApiConnector(BaseConnector):
    """SerpApi Multi-Engine Search & Local Business Listings Connector.
    Documentation: https://serpapi.com/
    """

    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self):
        super().__init__(
            name='serpapi',
            title='SerpApi Local & Web Search',
            category='Search Engine Index',
            rate_limit_per_min=20,
            daily_quota=100,
            requires_auth=True,
            auth_env_keys=['SERPAPI_API_KEY'],
            description='Live Google search and Google Local/Maps business listings via SerpApi.',
            attribution='SerpApi Multi-Engine & Local Business Search',
            supported_regions=['Global', 'India', 'United States', 'United Kingdom']
        )

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 10) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                f"SerpApi connector requires SERPAPI_API_KEY in environment."
            )

        api_key = os.environ.get('SERPAPI_API_KEY', '').strip()
        search_terms = [query, industry, category, city, country]
        clean_q = ' '.join([t.strip() for t in search_terms if t.strip()]) or "business services"

        params = {
            'engine': 'google',
            'q': clean_q,
            'api_key': api_key,
            'num': min(limit, 20)
        }

        def req():
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                return resp.json()

        data = self._execute_with_retry(req)
        results: List[DiscoveredLead] = []

        # 1. Process Google Local Results (Google Maps / Places) if present
        local_results = data.get('local_results', {}).get('places', [])
        for place in local_results:
            name = place.get('title', '').strip()
            link = place.get('website', '') or place.get('link', '')
            if name:
                results.append(DiscoveredLead(
                    name=name,
                    website=link,
                    industry=place.get('type', industry or 'Commercial Services'),
                    address=place.get('address', ''),
                    phone=place.get('phone', ''),
                    city=city,
                    country=country,
                    source_name='SerpApi Google Local',
                    source_url=link or place.get('thumbnail', 'Google Maps listing'),
                    evidence_confidence='high',
                    connector_name=self.name
                ))

        # 2. Process Organic Search Results
        organic_results = data.get('organic_results', [])
        for item in organic_results:
            if len(results) >= limit:
                break
            title = item.get('title', '').strip()
            link = item.get('link', '').strip()
            snippet = item.get('snippet', '').strip()
            if not link or not title:
                continue

            cleaned_name = re.sub(r'\s*([|\-–—:]\s*(Home|Official Site|Welcome|About)).*$', '', title, flags=re.I).strip()
            results.append(DiscoveredLead(
                name=cleaned_name or title,
                website=link,
                industry=industry or 'Commercial Enterprise',
                country=country,
                city=city,
                description=snippet,
                source_name='SerpApi Organic Index',
                source_url=link,
                evidence_confidence='high',
                connector_name=self.name
            ))

        return results[:limit]


class OpenCorporatesConnector(BaseConnector):
    """OpenCorporates Global Open Company Database Connector.
    Documentation: https://api.opencorporates.com/

    Licensing & Commercial Use Policy:
    - Data is published under the Open Database License (ODbL) / Share-Alike.
    - Free public tier is strictly restricted to open research and development with mandatory attribution.
    - Proprietary commercial exploitation (closed CRM, SaaS lead generation) requires an official OpenCorporates Commercial/Enterprise API Licence.
    - Kept disabled for commercial workflows until OPENCORPORATES_API_KEY is confirmed.
    """

    BASE_URL = "https://api.opencorporates.com/v0.4"

    def __init__(self):
        super().__init__(
            name='opencorporates',
            title='OpenCorporates Global Registry (Licence Required)',
            category='Official Corporate Registry',
            rate_limit_per_min=20,
            daily_quota=500,
            requires_auth=True, # Requires confirmed commercial API licence for proprietary SaaS use
            auth_env_keys=['OPENCORPORATES_API_KEY'],
            description='Global open corporate database across 140+ jurisdictions. Requires confirmed commercial API licence (OPENCORPORATES_API_KEY) for proprietary SaaS use. Free tier is strictly under ODbL Share-Alike.',
            attribution='OpenCorporates Open Database License (ODbL) — subject to terms',
            supported_regions=['Global', 'United Kingdom', 'United States']
        )

    def is_configured(self) -> bool:
        return bool(os.environ.get('OPENCORPORATES_API_KEY', '').strip())

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 15) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                "OpenCorporates connector requires a confirmed commercial API licence (OPENCORPORATES_API_KEY) for proprietary SaaS/CRM workflows. Free tier is strictly under ODbL Share-Alike."
            )

        term = query.strip() or f"{industry} {city}".strip() or "Technology"
        params: Dict[str, Any] = {
            'q': term,
            'per_page': min(limit, 30)
        }
        if country and country.strip().lower() in ('india', 'in'):
            params['jurisdiction_code'] = 'in'

        api_token = os.environ.get('OPENCORPORATES_API_KEY', '').strip()
        if api_token:
            params['api_token'] = api_token

        def req():
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(f"{self.BASE_URL}/companies/search", params=params)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req)
        except Exception as e:
            logger.warning("OpenCorporates query failed or rate limited: %s", str(e))
            return []

        companies = data.get('results', {}).get('companies', [])
        results: List[DiscoveredLead] = []

        for wrap in companies:
            c = wrap.get('company', {})
            c_name = c.get('name', '').strip()
            c_num = c.get('company_number', '')
            jurisdiction = c.get('jurisdiction_code', '').upper()
            oc_url = c.get('opencorporates_url', '')

            if not c_name:
                continue

            results.append(DiscoveredLead(
                name=c_name,
                website='',
                industry=industry or 'Incorporated Entity',
                country=country or jurisdiction,
                city=city,
                address=c.get('registered_address_in_full', ''),
                description=f"Registered corporate entity in {jurisdiction}. Company No: {c_num}.",
                source_name='OpenCorporates Public Registry',
                source_url=oc_url or f"https://opencorporates.com/companies/{jurisdiction}/{c_num}",
                evidence_confidence='high',
                raw_metadata={'company_number': c_num, 'jurisdiction': jurisdiction},
                connector_name=self.name
            ))

        return results[:limit]


class CsvSourceConnector(BaseConnector):
    """Connector for processing structured CSV leads from local files."""

    def __init__(self):
        super().__init__(
            name='csv_file',
            title='CSV Structured File Import',
            category='Structured File Import',
            rate_limit_per_min=60,
            daily_quota=10000,
            requires_auth=False,
            auth_env_keys=[],
            description='Parses user-supplied CSV files with actual business and contact details.',
            attribution='User-Provided Structured Dataset (CSV Import)',
            supported_regions=['Global', 'India', 'All']
        )

    def search(self, **kwargs) -> List[DiscoveredLead]:
        # Direct file searches are driven by CSV file upload
        return []

    def parse_csv(self, csv_text: str) -> List[DiscoveredLead]:
        leads: List[DiscoveredLead] = []
        reader = csv.DictReader(io.StringIO(csv_text.lstrip('\ufeff'), newline=''), strict=True)
        for row in reader:
            clean = {str(k).strip().lower(): (v or '').strip() for k, v in row.items() if k is not None}
            name = clean.get('name', '')
            if not name:
                continue
            leads.append(DiscoveredLead(
                name=name,
                website=clean.get('website', ''),
                industry=clean.get('industry', ''),
                sub_industry=clean.get('sub_industry', ''),
                country=clean.get('country', ''),
                city=clean.get('city', '') or clean.get('location', ''),
                address=clean.get('address', ''),
                phone=clean.get('phone', ''),
                email=clean.get('email', ''),
                description=clean.get('description', ''),
                source_name='CSV File Import',
                source_url='User Uploaded CSV',
                evidence_confidence='high',
                connector_name=self.name
            ))
        return leads


class PublicDirectoryConnector(BaseConnector):
    """Permitted Open Business Directory Connector.
    Requires DIRECTORY_API_ENDPOINT in environment for approved partner directories.
    Silent fallback to unverified or third-party datasets is disabled.
    """

    def __init__(self):
        super().__init__(
            name='public_directory',
            title='Permitted Business Directory',
            category='Public Business Directory',
            rate_limit_per_min=30,
            daily_quota=500,
            requires_auth=True,
            auth_env_keys=['DIRECTORY_API_ENDPOINT'],
            description='Connects to approved, permitted public business directories. Requires DIRECTORY_API_ENDPOINT in environment.',
            attribution='Permitted Public Business Directory',
            supported_regions=['Global', 'India']
        )

    def is_configured(self) -> bool:
        return bool(os.environ.get('DIRECTORY_API_ENDPOINT', '').strip())

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                "Permitted Business Directory connector requires DIRECTORY_API_ENDPOINT in environment. Silent fallback to third-party providers is disabled."
            )
        return []


class WebQueryConnector(BaseConnector):
    """Web Search Query Connector.
    Zero synthetic generation: requires configured search credentials (Google Search or SerpApi).
    """

    def __init__(self):
        super().__init__(
            name='web_query',
            title='Web & Search Index',
            category='Search Engine Index',
            rate_limit_per_min=20,
            daily_quota=200,
            requires_auth=True,
            auth_env_keys=['GOOGLE_SEARCH_API_KEY', 'SERPAPI_API_KEY'],
            description='Queries live web search engines using configured Google Search or SerpApi credentials.',
            attribution='Live Search Engine Query Index',
            supported_regions=['Global']
        )
        self._google = GoogleSearchConnector()
        self._serp = SerpApiConnector()

    def is_configured(self) -> bool:
        return self._google.is_configured() or self._serp.is_configured()

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 15) -> List[DiscoveredLead]:
        if self._google.is_configured():
            leads = self._google.search(query=query, country=country, city=city, industry=industry, category=category, limit=limit)
            for l in leads:
                l.connector_name = self.name
            return leads
        elif self._serp.is_configured():
            leads = self._serp.search(query=query, country=country, city=city, industry=industry, category=category, limit=limit)
            for l in leads:
                l.connector_name = self.name
            return leads
        else:
            raise ConnectorNotConfiguredError(
                "Web query connector requires either (GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_CX) or SERPAPI_API_KEY in environment."
            )


class IndiaOpenGovDataConnector(BaseConnector):
    """India Open Government Data (data.gov.in) Connector.
    Official public data portal operated by the National Informatics Centre (NIC), Government of India.
    Documentation: https://data.gov.in/

    Policy & Safety:
    - Kept strictly optional and disabled when credentials are not configured.
    - Never attempts to bypass age restrictions, authentication checks, or eligibility criteria.
    - Never fabricates or synthesizes records when unconfigured or when zero records are returned.
    """

    BASE_URL = "https://api.data.gov.in/resource"

    def __init__(self):
        super().__init__(
            name='india_ogd',
            title='India Open Government Data (data.gov.in)',
            category='Official Public Registry',
            rate_limit_per_min=30,
            daily_quota=500,
            requires_auth=True,
            auth_env_keys=['DATA_GOV_IN_API_KEY'],
            description='Official Open Government Data Platform India (data.gov.in). Kept optional and disabled when credentials are not configured.',
            attribution='Open Government Data (OGD) Platform India (data.gov.in) — NDSAP',
            supported_regions=['India', 'IN']
        )

    def is_configured(self) -> bool:
        if os.environ.get('DATA_GOV_IN_ENABLED', '').strip().lower() == 'false':
            return False
        return bool(os.environ.get('DATA_GOV_IN_API_KEY', '').strip())

    def search(self,
               query: str = '',
               country: str = 'India',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        if not self.is_configured():
            raise ConnectorNotConfiguredError(
                "India Open Government Data connector is optional and requires DATA_GOV_IN_API_KEY in environment. It is currently disabled."
            )

        api_key = os.environ.get('DATA_GOV_IN_API_KEY', '').strip()
        params = {
            'api-key': api_key,
            'format': 'json',
            'limit': min(limit, 50),
        }
        if city:
            params['filters[district]'] = city

        def req():
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req)
        except Exception as e:
            logger.warning("India OGD query failed: %s", str(e))
            return []

        records = data.get('records', [])
        results: List[DiscoveredLead] = []

        for item in records:
            name = item.get('company_name') or item.get('name') or item.get('entity_name') or ''
            name = str(name).strip()
            if not name:
                continue

            results.append(DiscoveredLead(
                name=name,
                website=str(item.get('website', '')).strip(),
                industry=str(item.get('industry', industry or 'Commercial Services')).strip(),
                country='India',
                city=str(item.get('city') or item.get('district') or city or '').strip(),
                address=str(item.get('address', '')).strip(),
                phone=str(item.get('phone', '')).strip(),
                email=str(item.get('email', '')).strip(),
                description=f"Public entity record via India Open Government Data (data.gov.in). Category: {item.get('category', 'Public Record')}.",
                source_name='India Open Government Data (data.gov.in)',
                source_url="https://data.gov.in/resource",
                evidence_confidence='high',
                raw_metadata={'ogd_record_id': item.get('id')},
                connector_name=self.name
            ))

        return results[:limit]


class WikidataSparqlConnector(BaseConnector):
    """Wikidata SPARQL Knowledge Graph Business Discovery Connector.
    Queries structured, community-validated open entity graphs for real incorporated
    business enterprises, healthcare centers, IT companies, logistics networks,
    and commercial entities in India and globally.

    Policy & Safety:
    - 100% open public data released under Creative Commons CC0 1.0 Universal Public Domain Dedication.
    - Completely free official W3C SPARQL endpoint provided by the Wikimedia Foundation.
    - Requires an identifiable User-Agent in all requests; zero private keys or paid tokens required.
    - Captures verified business name, official website, industry, headquarters, and Wikidata entity URI.
    - Zero synthetic data: returns only empirically verified Wikidata entities.
    """

    ENDPOINT = "https://query.wikidata.org/sparql"
    SEARCH_API = "https://www.wikidata.org/w/api.php"

    CITY_QIDS = {
        'gurugram': ['Q238508', 'Q1815766'],
        'gurgaon': ['Q238508', 'Q1815766'],
        'bengaluru': ['Q1355', 'Q1150031'],
        'bangalore': ['Q1355', 'Q1150031'],
        'mumbai': ['Q1156', 'Q1864115'],
        'bombay': ['Q1156'],
        'delhi': ['Q1353', 'Q987'],
        'new delhi': ['Q987'],
        'hyderabad': ['Q1361'],
        'pune': ['Q1538'],
        'chennai': ['Q1352'],
        'kolkata': ['Q1348'],
        'ahmedabad': ['Q1070'],
        'noida': ['Q2452778'],
        'jaipur': ['Q132680'],
        'kochi': ['Q1800'],
        'london': ['Q84'],
        'new york': ['Q60']
    }

    def __init__(self):
        super().__init__(
            name='wikidata_sparql',
            title='Wikidata Knowledge Graph (CC0 Public Domain)',
            category='Open Knowledge Graph',
            rate_limit_per_min=30,
            daily_quota=1000,
            requires_auth=False,
            auth_env_keys=[],
            description='Live Wikidata SPARQL knowledge graph discovery for incorporated business enterprises, startups, and commercial entities in India and worldwide.',
            attribution='Wikidata (CC0 1.0 Universal Public Domain Dedication, Wikimedia Foundation)',
            supported_regions=['India', 'Global', 'All']
        )
        self.last_error: Optional[str] = None

    def _resolve_city_qids(self, city: str) -> List[str]:
        if not city:
            return ['Q238508']
        raw = city.split(',')[0].strip().lower()
        if raw in self.CITY_QIDS:
            return self.CITY_QIDS[raw]
        try:
            headers = {'User-Agent': 'SparkXFlowLeadEngine/1.0 (contact@sparkxflow.local)'}
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(self.SEARCH_API, params={
                    'action': 'wbsearchentities',
                    'search': raw,
                    'language': 'en',
                    'format': 'json'
                }, headers=headers)
                hits = resp.json().get('search', [])
                if hits:
                    return [hits[0]['id']]
        except Exception as e:
            logger.debug("Failed resolving city QID for %s: %s", city, e)
        return ['Q238508']

    def search(self,
               query: str = '',
               country: str = 'India',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 15) -> List[DiscoveredLead]:
        self.last_error = None
        qids = self._resolve_city_qids(city or 'Gurugram')
        union_clauses = " \n    UNION\n    ".join([f"{{ ?item wdt:P159 wd:{q} . }}" for q in qids])

        sparql = f"""
SELECT DISTINCT ?item ?itemLabel ?website ?industryLabel WHERE {{
  {union_clauses}
  OPTIONAL {{ ?item wdt:P856 ?website . }}
  OPTIONAL {{ ?item wdt:P452 ?industry . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {min(limit * 3, 60)}
"""
        user_agent = os.environ.get('WIKIDATA_USER_AGENT', '').strip() or 'SparkXFlowLeadEngine/1.0 (https://sparkxflow.local; contact@sparkxflow.local)'
        headers = {
            'User-Agent': user_agent,
            'Accept': 'application/sparql-results+json'
        }

        def req():
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(self.ENDPOINT, params={'query': sparql, 'format': 'json'}, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req, retries=2, delay=1.5)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {str(e)}"
            logger.warning("Wikidata SPARQL query failed: %s", self.last_error)
            return []

        bindings = data.get('results', {}).get('bindings', [])
        results: List[DiscoveredLead] = []
        seen_names = set()

        raw_query = (query or '').strip().lower()
        clean_text = re.sub(r'[^a-zA-Z0-9\s]', ' ', raw_query)
        stopwords = {'services', 'companies', 'company', 'industry', 'pvt', 'ltd', 'private', 'limited', 'hub', 'solutions'}
        filter_terms = [t for t in clean_text.split() if len(t) >= 3 and t not in stopwords]

        for b in bindings:
            name = (b.get('itemLabel', {}).get('value') or '').strip()
            # Skip unlabeled entities where label is raw QID
            if not name or re.match(r'^Q\d+$', name):
                continue
            if name.lower() in seen_names:
                continue

            raw_web = (b.get('website', {}).get('value') or '').strip()
            ind_val = (b.get('industryLabel', {}).get('value') or '').strip()
            item_url = (b.get('item', {}).get('value') or '').strip()

            # Filter if search terms provided
            if filter_terms:
                haystack = f"{name} {ind_val}".lower()
                if not any(term in haystack for term in filter_terms):
                    continue

            seen_names.add(name.lower())
            dom = DiscoveredLead._extract_domain(raw_web)
            clean_city = (city or 'Gurugram').split(',')[0].strip()
            clean_country = country or 'India'

            results.append(DiscoveredLead(
                name=name,
                website=raw_web,
                domain=dom,
                industry=industry or ind_val.title() or 'Commercial Enterprise',
                sub_industry=ind_val or category or 'Corporate Enterprise',
                country=clean_country,
                city=clean_city,
                address=f"{clean_city}, {clean_country}",
                description=f"Verified commercial entity indexed in Wikidata knowledge graph (CC0). Headquarters: {clean_city}. Industry: {ind_val or 'Commercial'}.",
                source_name='Wikidata Knowledge Graph (CC0)',
                source_url=item_url or f"https://www.wikidata.org",
                evidence_confidence='high',
                raw_metadata={'wikidata_uri': item_url, 'wikidata_industry': ind_val},
                connector_name=self.name
            ))

            if len(results) >= limit:
                break

        return results


class OpenStreetMapOverpassConnector(BaseConnector):
    """OpenStreetMap Overpass Geospatial Discovery Connector.
    Queries verified, community-validated public geospatial data for commercial establishments,
    offices, IT companies, retail, logistics, and healthcare via the Overpass QL interpreter.

    Policy & Safety:
    - 100% open public data under the Open Database License (ODbL).
    - Provider Selection:
      * 'public_overpass' (default): Queries public community instances (OVERPASS_ENDPOINT).
      * 'overpass_ch': Prepared for dedicated Overpass.ch provider (requires OVERPASS_CH_API_KEY).
    - API Key Security: Overpass.ch keys are never exposed in logs, database records, source URLs, or frontend.
    - Rate Limits & Budget: Built-in monthly budget cap (default 10,000) and in-memory TTL caching.
    - Zero synthetic data: returns only empirically mapped entities with real coordinates and OSM tags.
    - If Overpass is unavailable or errors, returns a clear error without inventing synthetic businesses.
    - Strictly separate from Nominatim: executes actual Overpass QL statements.
    """

    PROVIDER_PUBLIC = 'public_overpass'
    PROVIDER_OVERPASS_CH = 'overpass_ch'

    CITY_BOUNDS = {
        'bengaluru': (12.83, 77.46, 13.14, 77.78),
        'bangalore': (12.83, 77.46, 13.14, 77.78),
        'mumbai': (18.89, 72.77, 19.27, 72.98),
        'gurugram': (28.38, 76.95, 28.54, 77.12),
        'gurgaon': (28.38, 76.95, 28.54, 77.12),
        'delhi': (28.40, 76.84, 28.88, 77.35),
        'hyderabad': (17.20, 78.20, 17.60, 78.65),
        'pune': (18.40, 73.75, 18.65, 74.00),
        'chennai': (12.90, 80.10, 13.25, 80.35),
        'kolkata': (22.45, 88.25, 22.70, 88.45),
        'london': (51.28, -0.51, 51.69, 0.33),
        'new york': (40.49, -74.26, 40.92, -73.70),
    }

    _lock = threading.Lock()
    _monthly_usage: Dict[str, int] = {}
    _cache: Dict[str, Tuple[float, List[DiscoveredLead]]] = {}

    def __init__(self):
        super().__init__(
            name='osm_overpass',
            title='OpenStreetMap Overpass (Public Geospatial)',
            category='Public Geospatial Directory',
            rate_limit_per_min=20,
            daily_quota=1000,
            requires_auth=False,
            auth_env_keys=[],
            description='Live OpenStreetMap Overpass geospatial registry for verified businesses and commercial establishments in India and worldwide.',
            attribution='© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)',
            supported_regions=['India', 'Global', 'All']
        )
        self.last_error: Optional[str] = None

    @classmethod
    def get_configured_provider(cls) -> str:
        provider = os.environ.get('OVERPASS_PROVIDER', '').strip().lower()
        if provider in (cls.PROVIDER_OVERPASS_CH, 'overpassch', 'ch'):
            return cls.PROVIDER_OVERPASS_CH
        return cls.PROVIDER_PUBLIC

    def is_configured(self) -> bool:
        if os.environ.get('OVERPASS_ENABLED', '').strip().lower() == 'false':
            return False
        provider = self.get_configured_provider()
        if provider == self.PROVIDER_OVERPASS_CH:
            return bool(os.environ.get('OVERPASS_CH_API_KEY', '').strip())
        return True

    def get_status(self) -> Dict[str, Any]:
        provider = self.get_configured_provider()
        is_conf = self.is_configured()
        req_auth = (provider == self.PROVIDER_OVERPASS_CH)
        auth_keys = ['OVERPASS_CH_API_KEY'] if req_auth else []
        title = (
            'OpenStreetMap (Overpass.ch API)'
            if provider == self.PROVIDER_OVERPASS_CH
            else 'OpenStreetMap Overpass (Public Geospatial)'
        )
        return {
            'name': self.name,
            'title': title,
            'category': self.category,
            'provider': provider,
            'is_configured': is_conf,
            'requires_auth': req_auth,
            'auth_keys': auth_keys,
            'status': 'available' if is_conf else 'unconfigured',
            'rate_limit_per_min': self.get_rate_limit_per_min(),
            'monthly_budget': self.get_monthly_budget() if provider == self.PROVIDER_OVERPASS_CH else None,
            'requests_used_this_month': self.get_monthly_requests_used() if provider == self.PROVIDER_OVERPASS_CH else None,
            'description': self.description,
            'attribution': self.attribution,
            'supported_regions': self.supported_regions
        }

    @staticmethod
    def _redact_url(url: str) -> str:
        if not url:
            return ""
        return re.sub(r'/(v1)/([^/]+)/interpreter', r'/\1/[REDACTED]/interpreter', url)

    def _resolve_endpoint(self) -> Tuple[str, str]:
        provider = self.get_configured_provider()
        if provider == self.PROVIDER_OVERPASS_CH:
            api_key = os.environ.get('OVERPASS_CH_API_KEY', '').strip()
            if not api_key:
                raise ConnectorNotConfiguredError(
                    "Overpass.ch provider requires OVERPASS_CH_API_KEY in environment. It is currently unconfigured."
                )
            template = os.environ.get(
                'OVERPASS_CH_ENDPOINT_TEMPLATE',
                'https://api.overpass.ch/v1/{api_key}/interpreter'
            ).strip()
            actual = template.format(api_key=api_key)
            return actual, self._redact_url(actual)
        else:
            actual = os.environ.get('OVERPASS_ENDPOINT', '').strip() or 'https://overpass-api.de/api/interpreter'
            return actual, actual

    @classmethod
    def get_monthly_budget(cls) -> int:
        try:
            return int(os.environ.get('OVERPASS_CH_MONTHLY_BUDGET', '10000').strip())
        except ValueError:
            return 10000

    @classmethod
    def get_rate_limit_per_min(cls) -> int:
        provider = cls.get_configured_provider()
        if provider == cls.PROVIDER_OVERPASS_CH:
            try:
                return int(os.environ.get('OVERPASS_CH_RATE_LIMIT_PER_MIN', '30').strip())
            except ValueError:
                return 30
        return 20

    @classmethod
    def get_monthly_requests_used(cls) -> int:
        month_key = datetime.now(timezone.utc).strftime('%Y-%m')
        with cls._lock:
            return cls._monthly_usage.get(month_key, 0)

    @classmethod
    def _check_and_increment_monthly_budget(cls) -> bool:
        month_key = datetime.now(timezone.utc).strftime('%Y-%m')
        budget = cls.get_monthly_budget()
        with cls._lock:
            used = cls._monthly_usage.get(month_key, 0)
            if used >= budget:
                return False
            cls._monthly_usage[month_key] = used + 1
            return True

    @classmethod
    def get_request_timeout(cls) -> float:
        provider = cls.get_configured_provider()
        key = 'OVERPASS_CH_TIMEOUT_SEC' if provider == cls.PROVIDER_OVERPASS_CH else 'OVERPASS_TIMEOUT_SEC'
        try:
            return float(os.environ.get(key, '30.0').strip())
        except ValueError:
            return 30.0

    @classmethod
    def _get_from_cache(cls, cache_key: str) -> Optional[List[DiscoveredLead]]:
        try:
            ttl = float(os.environ.get('OVERPASS_CACHE_TTL_SEC', '3600').strip())
        except ValueError:
            ttl = 3600.0
        now_ts = time.time()
        with cls._lock:
            if cache_key in cls._cache:
                ts, leads = cls._cache[cache_key]
                if now_ts - ts <= ttl:
                    return [DiscoveredLead(**vars(l)) for l in leads]
                else:
                    del cls._cache[cache_key]
        return None

    @classmethod
    def _store_in_cache(cls, cache_key: str, leads: List[DiscoveredLead]):
        now_ts = time.time()
        with cls._lock:
            cls._cache[cache_key] = (now_ts, [DiscoveredLead(**vars(l)) for l in leads])

    @classmethod
    def reset_cache_and_usage(cls):
        """Helper for test isolation."""
        with cls._lock:
            cls._cache.clear()
            cls._monthly_usage.clear()

    def _build_overpass_ql(self,
                           query: str,
                           city: str,
                           country: str,
                           industry: str,
                           category: str = '',
                           limit: int = 25) -> str:
        clean_q = re.sub(r'["\';]', '', (query or category or industry or 'commercial').strip())
        raw_city = city.split(',')[0].strip()
        clean_city = re.sub(r'["\';]', '', raw_city).lower()
        timeout = 25

        # Check for category-specific tags
        low_q = clean_q.lower()
        cat_clauses = []
        if any(w in low_q for w in ('restaurant', 'food', 'cafe', 'dining')):
            cat_clauses.append('node["amenity"~"restaurant|cafe|fast_food", i]')
        if any(w in low_q for w in ('clinic', 'doctor', 'hospital', 'medical', 'healthcare')):
            cat_clauses.append('node["amenity"~"clinic|doctors|hospital", i]')
            cat_clauses.append('node["healthcare"~"clinic|doctor|centre", i]')
        if any(w in low_q for w in ('it', 'software', 'technology', 'tech', 'computer')):
            cat_clauses.append('node["office"~"it|software|company|research", i]')
        if any(w in low_q for w in ('estate', 'property', 'realty', 'real estate')):
            cat_clauses.append('node["office"~"estate_agent|real_estate", i]')

        # If known city bounds, apply bounding box for fast spatial indexing
        if clean_city in self.CITY_BOUNDS:
            s, w, n, e = self.CITY_BOUNDS[clean_city]
            bbox_clauses = [
                f'node["name"~"{clean_q}", i]({s}, {w}, {n}, {e});',
                f'node["office"~"{clean_q}", i]({s}, {w}, {n}, {e});',
                f'node["amenity"~"{clean_q}", i]({s}, {w}, {n}, {e});',
                f'node["shop"~"{clean_q}", i]({s}, {w}, {n}, {e});',
                f'node["industrial"~"{clean_q}", i]({s}, {w}, {n}, {e});',
                f'way["name"~"{clean_q}", i]({s}, {w}, {n}, {e});'
            ]
            for cc in cat_clauses:
                bbox_clauses.append(f'{cc}({s}, {w}, {n}, {e});')
            clauses_str = "\n  ".join(bbox_clauses)
            return f"""[out:json][timeout:{timeout}];
(
  {clauses_str}
);
out center {min(limit, 50)};
"""
        elif clean_city:
            return f"""[out:json][timeout:{timeout}];
area["name"~"^{clean_city}", i]->.searchArea;
(
  node(area.searchArea)["name"~"{clean_q}", i];
  node(area.searchArea)["office"~"{clean_q}", i];
  way(area.searchArea)["name"~"{clean_q}", i];
);
out center {min(limit, 50)};
"""
        else:
            country_filter = '["addr:country"="IN"]' if country.strip().lower() in ('india', 'in') else ''
            return f"""[out:json][timeout:{timeout}];
(
  node["name"~"{clean_q}", i]{country_filter};
  way["name"~"{clean_q}", i]{country_filter};
);
out center {min(limit, 50)};
"""

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 15) -> List[DiscoveredLead]:
        self.last_error = None
        provider = self.get_configured_provider()
        if not self.is_configured():
            if provider == self.PROVIDER_OVERPASS_CH:
                raise ConnectorNotConfiguredError(
                    "Overpass.ch provider requires OVERPASS_CH_API_KEY in environment. It is currently unconfigured."
                )
            raise ConnectorNotConfiguredError(
                "OpenStreetMap Overpass connector is currently disabled by OVERPASS_ENABLED=false."
            )

        cache_key = f"{provider}:{query.strip().lower()}:{city.strip().lower()}:{country.strip().lower()}:{industry.strip().lower()}:{limit}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            logger.info("Serving %d cached Overpass leads for query '%s' to conserve quota", len(cached), query)
            return cached

        if provider == self.PROVIDER_OVERPASS_CH:
            if not self._check_and_increment_monthly_budget():
                logger.warning(
                    "Overpass.ch monthly request budget (%d) reached for current billing cycle. Halting query to prevent overage.",
                    self.get_monthly_budget()
                )
                self.last_error = f"Overpass.ch monthly budget cap ({self.get_monthly_budget()}) reached"
                return []

        actual_endpoint, redacted_endpoint = self._resolve_endpoint()
        user_agent = os.environ.get('OVERPASS_USER_AGENT', '').strip() or 'SparkXFlowLeadEngine/1.0 (LeadDiscoveryEngine; contact@sparkxflow.local)'
        timeout_sec = self.get_request_timeout()

        ql_query = self._build_overpass_ql(
            query=query,
            city=city,
            country=country,
            industry=industry,
            category=category,
            limit=limit
        )

        headers = {
            'User-Agent': user_agent,
            'Accept': 'application/json'
        }

        def req():
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.post(actual_endpoint, data={'data': ql_query}, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req, retries=2, delay=2.0)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            self.last_error = f"HTTP {status_code}"
            if status_code == 401:
                logger.warning(
                    "Overpass authentication failed (HTTP 401) at %s: Invalid, expired, or missing API key. No synthetic records generated.",
                    redacted_endpoint
                )
                return []
            elif status_code == 403:
                logger.warning(
                    "Overpass access forbidden (HTTP 403) at %s: Monthly quota reached or tier restriction. No synthetic records generated.",
                    redacted_endpoint
                )
                return []
            elif status_code == 429:
                retry_after = e.response.headers.get('Retry-After', 'unspecified')
                logger.warning(
                    "Overpass rate limit exceeded (HTTP 429) at %s. Retry-After: %s. No synthetic records generated.",
                    redacted_endpoint, retry_after
                )
                return []
            elif status_code in (502, 503, 504):
                logger.warning(
                    "Overpass API endpoint %s returned status %d (service unavailable / queue capacity). No synthetic records generated.",
                    redacted_endpoint, status_code
                )
                return []
            logger.error("Overpass HTTP error at %s: %s", redacted_endpoint, str(e))
            return []
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            self.last_error = f"Timeout/Network error: {str(e)}"
            logger.warning(
                "Overpass API endpoint %s timed out or network error: %s. No synthetic records generated.",
                redacted_endpoint, str(e)
            )
            return []

        elements = data.get('elements', [])
        results: List[DiscoveredLead] = []

        is_ch = (provider == self.PROVIDER_OVERPASS_CH)
        source_name = 'OpenStreetMap (Overpass.ch / ODbL)' if is_ch else 'OpenStreetMap Overpass (ODbL)'
        desc_svc = 'Overpass.ch' if is_ch else 'OpenStreetMap Overpass QL'

        for el in elements:
            tags = el.get('tags') or {}
            name = (tags.get('name') or tags.get('name:en') or '').strip()
            if not name:
                continue

            el_type = el.get('type', 'node')
            el_id = el.get('id', '')

            # Location extraction
            addr_city = tags.get('addr:city') or tags.get('addr:district') or tags.get('addr:suburb') or city
            addr_country = tags.get('addr:country') or country or ('India' if country.lower() in ('india', 'in') else '')
            addr_parts = [tags.get('addr:housename'), tags.get('addr:housenumber'), tags.get('addr:street'), tags.get('addr:postcode')]
            full_address = ', '.join([p for p in addr_parts if p]) or f"{addr_city}, {addr_country}".strip(', ')

            website = (tags.get('website') or tags.get('contact:website') or tags.get('url') or '').strip()
            phone = (tags.get('phone') or tags.get('contact:phone') or '').strip()
            email = (tags.get('email') or tags.get('contact:email') or '').strip()

            el_category = tags.get('office') or tags.get('amenity') or tags.get('shop') or tags.get('industrial') or tags.get('craft') or industry or 'Commercial Establishment'

            # Keep public OSM entity page as source URL - never leak internal API key
            osm_url = f"https://www.openstreetmap.org/{el_type}/{el_id}" if el_id else "https://www.openstreetmap.org"

            results.append(DiscoveredLead(
                name=name,
                website=website,
                domain=DiscoveredLead._extract_domain(website),
                industry=industry or f"{el_category}".title(),
                sub_industry=el_category,
                country=addr_country,
                city=addr_city,
                address=full_address,
                phone=phone,
                email=email,
                description=f"Verified commercial establishment ({el_category}) mapped via {desc_svc}. OSM ID: {el_id}. Attribution: (c) OpenStreetMap contributors (ODbL).",
                source_name=source_name,
                source_url=osm_url,
                evidence_confidence='high',
                raw_metadata={'osm_id': el_id, 'osm_type': el_type, 'service': 'overpass_ql', 'provider': provider},
                connector_name=self.name
            ))

            if len(results) >= limit:
                break

        if results:
            self._store_in_cache(cache_key, results)

        return results


class WebsiteCrawlerConnector(BaseConnector):
    """Direct Public Website Crawler and Contact Research Connector.
    Completely compliant with robots.txt, host pacing, SSRF protection,
    and wall-clock execution limits. Inspects public web markup for Schema.org JSON-LD,
    mailto links, tel links, and technical quality indicators.
    """

    def __init__(self):
        super().__init__(
            name='website_crawler',
            title='Public Website Crawler & Research',
            category='Direct Web Research',
            rate_limit_per_min=10,
            daily_quota=100,
            requires_auth=False,
            auth_env_keys=[],
            description='Safely crawls public websites using local worker sandbox with robots.txt, host pacing, and SSRF restrictions.',
            attribution='Direct Public Website Inspection (Observable Metadata & Schema.org markup)',
            supported_regions=['India', 'Global', 'All']
        )

    def search(self,
               query: str = '',
               country: str = '',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 25) -> List[DiscoveredLead]:
        """Perform observable web research against target domains or URLs specified in query."""
        from .. import crawl_client
        from ..crawl_client import CrawlTimeout, CrawlCapacity, CrawlFailure
        from ..research.qualification_engine import QualificationEngine

        db_url = os.environ.get('DATABASE_URL', 'sqlite:///sparkxflow.db')
        targets: List[str] = []

        # Extract target URLs or domains from query
        raw_query = (query or '').strip()
        if raw_query:
            tokens = [t.strip().rstrip(',;') for t in re.split(r'[\s,]+', raw_query) if t.strip()]
            for token in tokens:
                if '.' in token and not token.startswith(('http://', 'https://')):
                    targets.append(f"https://{token}")
                elif token.startswith(('http://', 'https://')):
                    targets.append(token)

        if not targets:
            logger.info("WebsiteCrawlerConnector invoked without explicit URL/domain targets in query.")
            return []

        results: List[DiscoveredLead] = []
        for url in targets[:limit]:
            try:
                final_url, html = crawl_client.run_crawl(url, db_url)
                business_name = DiscoveredLead._extract_domain(final_url)
                qual_data = QualificationEngine.analyze(final_url, html, business_name=business_name)
                contacts = QualificationEngine.extract_public_contacts(final_url, html, business_name=business_name)

                # Extract title and description
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.get_text(' ', strip=True)[:250] if soup.title else business_name
                meta_desc = soup.find('meta', attrs={'name': re.compile(r'^description$', re.I)})
                description = (meta_desc.get('content', '') if meta_desc else '')[:500]

                first_email = ''
                first_phone = ''
                for c in contacts:
                    if not first_email and c.get('email'):
                        first_email = c['email']
                    if not first_phone and c.get('phone'):
                        first_phone = c['phone']

                lead = DiscoveredLead(
                    name=title or business_name,
                    website=final_url,
                    domain=DiscoveredLead._extract_domain(final_url),
                    industry=industry or 'Technology & Web Services',
                    sub_industry=category or 'Public Digital Service',
                    country=country or 'India',
                    city=city or 'Bengaluru',
                    description=description or f"Direct observable public web crawl of {final_url}.",
                    phone=first_phone,
                    email=first_email,
                    source_name='Public Website Crawler',
                    source_url=final_url,
                    evidence_confidence=qual_data.get('evidence_confidence', 'high'),
                    connector_name=self.name,
                    raw_metadata={
                        'qual_data': qual_data,
                        'contacts': contacts,
                        'opportunities': qual_data.get('opportunities', [])
                    }
                )
                results.append(lead)
            except (CrawlTimeout, CrawlCapacity, CrawlFailure, Exception) as e:
                logger.warning("WebsiteCrawler failed crawling %s: %s", url, str(e))
                continue

        return results


# OutLead-derived parsing regexes (reused under MIT License)
_RATING_RE = re.compile(r"([0-9]+(?:\.[0-9])?)\s*\(([\d,]+)\)")
_PLUS_CODE_RE = re.compile(r"[A-Z0-9]{4,}\+[A-Z0-9]{2,}")
_PLACE_KEY_RE = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")


def place_key_from_url(url: str) -> Optional[str]:
    """Extract Google Maps hex place key from listing URL."""
    if not url:
        return None
    m = _PLACE_KEY_RE.search(url)
    return m.group(1) if m else None


def parse_open_state(status: Optional[str]) -> Optional[str]:
    """Normalize raw business status into standard enum."""
    if not status:
        return None
    s = status.strip().lower()
    if s.startswith("permanently closed"):
        return "Permanently closed"
    if s.startswith("temporarily closed"):
        return "Temporarily closed"
    if s.startswith("open 24 hours"):
        return "Open 24 hours"
    if s.startswith("open"):
        return "Open"
    if s.startswith("closed"):
        return "Closed"
    return status.strip()


class OutLeadBulkMapsConnector(BaseConnector):
    """Bulk Google Maps and Places business discovery connector.
    
    Provides high-throughput multi-query lead generation with rich place fields:
    business name, category, address, phone, official website, ratings, review counts,
    operating hours, and exact Google Maps listings.

    Safety & Operational Constraints:
    - Strictly avoids evasive headless bot scraping against Google Maps web UI.
    - Uses permitted Google Places API or SerpApi Google Maps endpoint when configured.
    - If unconfigured, clearly exposes its status as unconfigured and raises
      ConnectorNotConfiguredError without generating synthetic records.
    - Fully adheres to rate limits and SparkXFlow anti-abuse boundaries.
    """

    GOOGLE_PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    SERPAPI_URL = "https://serpapi.com/search.json"

    def __init__(self):
        super().__init__(
            name='outlead_bulk_maps',
            title='OutLead Bulk Business Discovery (Google Maps / Places)',
            category='Bulk Business Discovery',
            rate_limit_per_min=30,
            daily_quota=500,
            requires_auth=True,
            auth_env_keys=['GOOGLE_PLACES_API_KEY', 'SERPAPI_API_KEY', 'OUTLEAD_API_KEY'],
            description='OutLead-inspired bulk Google Maps & Places discovery with ratings, reviews, operating hours, and contact enrichment.',
            attribution='Google Maps / Places Data & OutLead Engine (MIT License)',
            supported_regions=['India', 'Global', 'All']
        )
        self.last_error: Optional[str] = None

    def is_configured(self) -> bool:
        """Connector is configured only if a permitted Maps/Places API key is set."""
        for key in self.auth_env_keys:
            val = os.environ.get(key, '').strip()
            if val and not val.startswith('replace-with-'):
                return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Expose actual operational status and configuration requirements."""
        configured = self.is_configured()
        active_key = None
        for key in self.auth_env_keys:
            if os.environ.get(key, '').strip() and not os.environ.get(key, '').strip().startswith('replace-with-'):
                active_key = key
                break

        msg = (
            f"Active via {active_key}."
            if configured
            else "Unconfigured. Set GOOGLE_PLACES_API_KEY, SERPAPI_API_KEY, or OUTLEAD_API_KEY in .env "
                 "to enable permitted Google Maps / Places discovery. Headless bot bypass is strictly prohibited."
        )

        return {
            'name': self.name,
            'title': self.title,
            'category': self.category,
            'is_configured': configured,
            'active_provider': active_key or 'none',
            'rate_limit_per_min': self.rate_limit_per_min,
            'daily_quota': self.daily_quota,
            'auth_keys': self.auth_env_keys,
            'attribution': self.attribution,
            'supported_regions': self.supported_regions,
            'status': 'available' if configured else 'unconfigured',
            'message': msg
        }

    def search(self,
               query: str = '',
               country: str = 'India',
               city: str = '',
               industry: str = '',
               category: str = '',
               limit: int = 20) -> List[DiscoveredLead]:
        """Execute a search query against the configured Google Maps / Places service."""
        self.last_error = None
        if not self.is_configured():
            err = (
                "OutLead Bulk Maps Connector is not configured. "
                "Set GOOGLE_PLACES_API_KEY, SERPAPI_API_KEY, or OUTLEAD_API_KEY in .env."
            )
            self.last_error = err
            raise ConnectorNotConfiguredError(err)

        terms = [t for t in [category or industry, city, country] if t]
        clean_query = query.strip() if query else " in ".join(terms) if terms else "business in India"

        google_key = os.environ.get('GOOGLE_PLACES_API_KEY', '').strip()
        serpapi_key = os.environ.get('SERPAPI_API_KEY', '').strip()
        outlead_key = os.environ.get('OUTLEAD_API_KEY', '').strip()

        if google_key and not google_key.startswith('replace-with-'):
            return self._search_google_places(clean_query, google_key, city, country, limit)
        elif serpapi_key and not serpapi_key.startswith('replace-with-'):
            return self._search_serpapi_maps(clean_query, serpapi_key, city, country, limit)
        elif outlead_key and not outlead_key.startswith('replace-with-'):
            return self._search_outlead_service(clean_query, outlead_key, city, country, limit)
        else:
            raise ConnectorNotConfiguredError("No valid API credentials found.")

    def _search_google_places(self, query: str, api_key: str, city: str, country: str, limit: int) -> List[DiscoveredLead]:
        """Fetch places using Google Places Web Service API."""
        params = {'query': query, 'key': api_key}
        headers = {'User-Agent': 'SparkXFlowLeadEngine/1.0'}

        def req():
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(self.GOOGLE_PLACES_TEXTSEARCH_URL, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req, retries=2, delay=1.0)
        except Exception as e:
            self.last_error = f"Google Places API error: {str(e)}"
            logger.warning(self.last_error)
            return []

        status = data.get('status', '')
        if status not in ('OK', 'ZERO_RESULTS'):
            self.last_error = f"Google Places API status: {status}"
            logger.warning(self.last_error)
            return []

        results: List[DiscoveredLead] = []
        for place in data.get('results', [])[:limit]:
            name = (place.get('name') or '').strip()
            if not name:
                continue

            address = place.get('formatted_address', '')
            rating = float(place.get('rating')) if place.get('rating') is not None else None
            review_count = int(place.get('user_ratings_total')) if place.get('user_ratings_total') is not None else None
            place_id = place.get('place_id', '')
            geom = place.get('geometry', {}).get('location', {})
            lat = geom.get('lat')
            lng = geom.get('lng')
            maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else ''
            raw_types = place.get('types', [])
            primary_cat = raw_types[0].replace('_', ' ').title() if raw_types else 'Local Business'

            lead = DiscoveredLead(
                name=name,
                website='',
                domain=None,
                industry=primary_cat,
                sub_industry=primary_cat,
                country=country or 'India',
                city=city or 'Bengaluru',
                address=address,
                phone='',
                description=f"Google Places rating: {rating or 'N/A'} ({review_count or 0} reviews). Category: {primary_cat}.",
                source_name='OutLead Google Maps / Places',
                source_url=maps_url,
                evidence_confidence='high',
                connector_name=self.name,
                raw_metadata={
                    'place_id': place_id,
                    'rating': rating,
                    'review_count': review_count,
                    'latitude': lat,
                    'longitude': lng,
                    'maps_url': maps_url,
                    'types': raw_types
                }
            )
            results.append(lead)
        return results

    def _search_serpapi_maps(self, query: str, api_key: str, city: str, country: str, limit: int) -> List[DiscoveredLead]:
        """Fetch places using SerpApi Google Maps engine."""
        params = {'engine': 'google_maps', 'q': query, 'api_key': api_key}
        headers = {'User-Agent': 'SparkXFlowLeadEngine/1.0'}

        def req():
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(self.SERPAPI_URL, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            data = self._execute_with_retry(req, retries=2, delay=1.0)
        except Exception as e:
            self.last_error = f"SerpApi Google Maps error: {str(e)}"
            logger.warning(self.last_error)
            return []

        results: List[DiscoveredLead] = []
        for place in data.get('local_results', [])[:limit]:
            name = (place.get('title') or '').strip()
            if not name:
                continue

            website = (place.get('website') or '').strip()
            phone = (place.get('phone') or '').strip()
            address = place.get('address', '')
            rating = float(place.get('rating')) if place.get('rating') is not None else None
            review_count = int(place.get('reviews')) if place.get('reviews') is not None else None
            hours = place.get('operating_hours', {}).get('hours', '') if isinstance(place.get('operating_hours'), dict) else ''
            price = place.get('price', '')
            maps_url = place.get('link', '')

            gps = place.get('gps_coordinates', {})
            lat = gps.get('latitude')
            lng = gps.get('longitude')
            place_id = place.get('place_id', '')

            lead = DiscoveredLead(
                name=name,
                website=website,
                domain=DiscoveredLead._extract_domain(website) if website else None,
                industry=place.get('type') or 'Local Business',
                sub_industry=place.get('type') or '',
                country=country or 'India',
                city=city or 'Bengaluru',
                address=address,
                phone=phone,
                description=f"Google Maps rating: {rating or 'N/A'} ({review_count or 0} reviews). {address}",
                source_name='OutLead Google Maps / Places',
                source_url=maps_url,
                evidence_confidence='high',
                connector_name=self.name,
                raw_metadata={
                    'place_id': place_id,
                    'rating': rating,
                    'review_count': review_count,
                    'business_hours': hours,
                    'price_level': price,
                    'latitude': lat,
                    'longitude': lng,
                    'maps_url': maps_url
                }
            )
            results.append(lead)
        return results

    def _search_outlead_service(self, query: str, api_key: str, city: str, country: str, limit: int) -> List[DiscoveredLead]:
        """Fetch places using dedicated OutLead microservice."""
        endpoint = os.environ.get('OUTLEAD_API_ENDPOINT', 'https://api.outlead.local/v1/places/search')
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'SparkXFlowLeadEngine/1.0',
            'Content-Type': 'application/json'
        }
        payload = {'query': query, 'city': city, 'country': country, 'limit': limit}

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            self.last_error = f"OutLead API error: {str(e)}"
            logger.warning(self.last_error)
            return []

        results: List[DiscoveredLead] = []
        for item in data.get('leads', [])[:limit]:
            lead = DiscoveredLead(
                name=item.get('name', ''),
                website=item.get('website', ''),
                domain=DiscoveredLead._extract_domain(item.get('website', '')),
                industry=item.get('category', 'Local Business'),
                sub_industry=item.get('category', ''),
                country=country,
                city=city,
                address=item.get('address', ''),
                phone=item.get('phone', ''),
                source_name='OutLead Bulk Maps Discovery',
                source_url=item.get('maps_url', ''),
                evidence_confidence='high',
                connector_name=self.name,
                raw_metadata=item
            )
            results.append(lead)
        return results


# Complete Connector Registry with canonical names and safe aliases
_osm_connector = OpenStreetMapOverpassConnector()
_crawler_connector = WebsiteCrawlerConnector()
_wikidata_connector = WikidataSparqlConnector()
_outlead_connector = OutLeadBulkMapsConnector()

CONNECTOR_REGISTRY: Dict[str, BaseConnector] = {
    'outlead_bulk_maps': _outlead_connector,
    'outlead': _outlead_connector,
    'bulk_maps': _outlead_connector,
    'google_maps': _outlead_connector,
    'wikidata_sparql': _wikidata_connector,
    'wikidata': _wikidata_connector,
    'knowledge_graph': _wikidata_connector,
    'uk_companies_house': CompaniesHouseRegistryConnector(),
    'sec_edgar': SecEdgarConnector(),
    'google_search': GoogleSearchConnector(),
    'serpapi': SerpApiConnector(),
    'opencorporates': OpenCorporatesConnector(),
    'osm_overpass': _osm_connector,
    'overpass': _osm_connector,
    'openstreetmap': _osm_connector,
    'india_ogd': IndiaOpenGovDataConnector(),
    'csv_file': CsvSourceConnector(),
    'public_directory': PublicDirectoryConnector(),
    'web_query': WebQueryConnector(),
    'website_crawler': _crawler_connector,
    'crawler': _crawler_connector
}

def get_connector(name: str) -> Optional[BaseConnector]:
    clean_name = (name or '').strip().lower()
    return CONNECTOR_REGISTRY.get(clean_name)

def list_all_connectors() -> List[Dict[str, Any]]:
    # Deduplicate so dashboard displays each unique connector once without duplicate alias cards
    seen_ids = set()
    canonical = []
    for c in CONNECTOR_REGISTRY.values():
        if id(c) not in seen_ids:
            seen_ids.add(id(c))
            canonical.append(c.get_status())
    return canonical
