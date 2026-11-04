"""SparkXFlow foundation: authenticated imports, evidence-backed research and review.
No outreach provider is connected and this service cannot send email.
"""
import csv
import hmac
import io
import json
import os
import re
import socket
import ipaddress
import ssl
import http.client
import urllib.parse
import urllib.robotparser
import uuid
import unicodedata
import threading
import time
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Text, DateTime, Integer, Float, ForeignKey, select, inspect, text, update, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from .crawl_client import run_crawl, CrawlTimeout, CrawlCapacity, CrawlFailure
from .models import LeadQualification
from .research.qualification_engine import QualificationEngine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///./sparkxflow.db')
_db_url=make_url(DATABASE_URL)
if _db_url.get_backend_name() not in ('sqlite','postgresql'):
    raise RuntimeError('Only SQLite and local PostgreSQL are supported')
if _db_url.get_backend_name()=='postgresql' and _db_url.host not in ('localhost','127.0.0.1','::1'):
    raise RuntimeError('Only local PostgreSQL is supported')
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')
if not ADMIN_TOKEN or len(ADMIN_TOKEN) < 8 or ADMIN_TOKEN.startswith('replace-with-'):
    raise RuntimeError('Set ADMIN_TOKEN to a secret of at least 8 characters in .env')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())

from .models import (
    Base, Business, DuplicateReview, ResearchHistory, IdentityGuard, BusinessDomain,
    ImportBatch, ImportCandidate, BusinessSource, BusinessRelationship, ReviewResolution,
    CrawlerControl, CrawlerLease, CrawlerHostLimit,
    BusinessProfile, SearchJob, DiscoveryHypothesis, SourceConnector, LeadQualification,
    Contact, Campaign, OutreachMessage, InboxMessage, FollowUpTask, SuppressionEntry,
    SalesPipelineItem, SystemIntegration, AutomationJob
)

def assert_database_ready():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    head = ScriptDirectory.from_config(Config(str(ROOT / 'backend' / 'alembic.ini'))).get_current_head()
    with engine.connect() as connection:
        if 'alembic_version' not in inspect(connection).get_table_names():
            raise RuntimeError('Database is not migrated. Back up first, then run: python backend/manage.py migrate')
        versions = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions != [head]:
            raise RuntimeError('Database revision is not current. Back up first, then run: python backend/manage.py migrate')

@asynccontextmanager
async def lifespan(_app):
    assert_database_ready()
    Base.metadata.create_all(engine)
    yield

def db():
    with SessionLocal() as session: yield session

_auth_lock=threading.Lock()
_auth_failures=[]
def auth(authorization: str = Header(default='')):
    moment=time.monotonic()
    with _auth_lock:
        _auth_failures[:]=[t for t in _auth_failures if moment-t<60]
        if len(_auth_failures)>=10: raise HTTPException(429,'Too many authentication failures; try again in one minute')
        expected = 'Bearer ' + ADMIN_TOKEN
        if not hmac.compare_digest(authorization.encode('utf-8'), expected.encode('utf-8')):
            _auth_failures.append(moment)
            raise HTTPException(401, 'Invalid or missing administrator token')


app = FastAPI(title='SparkXFlow Lead Intelligence Engine', version='0.1.0', docs_url=None, redoc_url=None, lifespan=lifespan)
# This application is a local-only prototype. Do not trust proxy forwarding headers.
logger=logging.getLogger('sparkxflow')
if not logger.handlers:
    handler=logging.StreamHandler(); handler.setFormatter(logging.Formatter('%(message)s')); logger.addHandler(handler)
logger.setLevel(logging.INFO)

def local_host(value):
    try:
        host=urllib.parse.urlsplit('//'+value).hostname
        if host=='localhost': return True
        return bool(host and ipaddress.ip_address(host).is_loopback)
    except (ValueError,TypeError): return False

@app.middleware('http')
async def local_security_and_log(request:Request, call_next):
    request_id=str(uuid.uuid4())
    peer=request.client.host if request.client else ''
    host=request.headers.get('host','')
    try: peer_ok=ipaddress.ip_address(peer).is_loopback
    except ValueError: peer_ok=False
    origin=request.headers.get('origin')
    origin_ok=True
    if origin:
        try:
            parsed=urllib.parse.urlsplit(origin)
            origin_ok=parsed.scheme in ('http','https') and local_host(parsed.netloc) and parsed.netloc.lower()==host.lower()
        except ValueError: origin_ok=False
    if not peer_ok or not local_host(host) or not origin_ok:
        response=JSONResponse(status_code=403,content={'detail':'Local access only'})
    else:
        try: response=await call_next(request)
        except Exception as exc:
            logger.error(json.dumps({'event':'request_error','request_id':request_id,'exception_type':type(exc).__name__}))
            response=JSONResponse(status_code=500,content={'detail':'Unexpected server error','request_id':request_id})
    response.headers['X-Request-ID']=request_id
    route=request.scope.get('route')
    logger.info(json.dumps({'event':'request','request_id':request_id,'method':request.method,'route':getattr(route,'path','unmatched'),'status':response.status_code}))
    return response

class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str = Field(default='', max_length=2048)
    industry: str = Field(default='', max_length=120)
    location: str = Field(default='', max_length=200)
    source: str = Field(default='Manual import', max_length=2048)
class ReviewAction(BaseModel):
    decision: str
    matched_business_id: Optional[str] = None
class ImportIn(BaseModel):
    csv_text: str = Field(max_length=100_000)

def normalize_url(raw):
    raw = raw.strip()
    if not raw: return '', None
    if any(ord(c)<32 or ord(c)==127 for c in raw): raise HTTPException(422,'Invalid website URL')
    if '://' in raw and not re.match(r'^https?://',raw,re.I): raise HTTPException(422,'Only HTTP(S) websites are allowed')
    if not re.match(r'^https?://', raw, re.I): raw = 'https://' + raw
    try:
        p = urllib.parse.urlsplit(raw)
        host = (p.hostname or '').lower().rstrip('.').encode('idna').decode('ascii')
        if p.scheme.lower() not in ('http', 'https') or not host or len(host)>253 or p.username or p.password or p.port not in (None, 80, 443): raise ValueError()
        try: ipaddress.ip_address(host)
        except ValueError:
            labels=host.split('.')
            if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in labels): raise ValueError()
        if (p.scheme.lower() == 'http' and p.port not in (None,80)) or (p.scheme.lower() == 'https' and p.port not in (None,443)): raise ValueError()
        host_for_url = '['+host+']' if ':' in host else host
        url = urllib.parse.urlunsplit((p.scheme.lower(),host_for_url, p.path or '/',p.query,''))
        if len(url)>2048: raise ValueError()
        domain = host[4:] if host.startswith('www.') else host
        return url, domain
    except (ValueError, UnicodeError): raise HTTPException(422, 'Invalid website URL; use public HTTP(S) on the default port')

def presentation_report(raw):
    if not raw: return None
    try: report=json.loads(raw)
    except (ValueError, TypeError): return None
    if not isinstance(report,dict) or not isinstance(report.get('evidence'),list) or not isinstance(report.get('opportunities'),list): return None
    for e in report['evidence']:
        if not isinstance(e,dict) or not all(isinstance(e.get(k),str) for k in ('fact','url','collected_at','confidence')): return None
        try:
            if urllib.parse.urlsplit(e['url']).scheme not in ('http','https'): return None
        except ValueError: return None
    for o in report['opportunities']:
        if not isinstance(o,dict) or not all(isinstance(o.get(k),str) for k in ('service','reason','confidence')): return None
    # Numeric legacy signals are retained in storage, but never presented as evidence of demand.
    opportunities=report.get('opportunities')
    if isinstance(opportunities,list):
        for o in opportunities:
            if isinstance(o,dict):
                o['score']=None
                if o.get('service')=='Website development':
                    o['reason']='Website needs are unknown. Review the technical observations; a viewport tag alone does not establish a service opportunity.'
                    o['confidence']='unknown'
    report['limitations']='Observed page characteristics only. Service needs, intent, budget and conversion potential are unknown without supporting evidence.'
    return report

def business_domain(b):
    if b.website:
        try: return normalize_url(b.website)[1]
        except HTTPException: pass
    return b.domain

def serialize(b):
    return {'id':b.id,'name':b.name,'website':b.website,'domain':business_domain(b),'industry':b.industry,'location':b.location,'source':b.source,'created_at':b.created_at.isoformat(),'researched_at':b.researched_at.isoformat() if b.researched_at else None,'report':presentation_report(b.report)}

def normalized_name(value):
    value=unicodedata.normalize('NFKC',value).casefold()
    return ' '.join(re.findall(r'[^\W_]+',value,flags=re.UNICODE))

def candidate_matches(item, domain, session):
    name=normalized_name(item.name)
    location=normalized_name(item.location)
    matches=[]
    for existing, indexed_domain in session.execute(select(Business,BusinessDomain.domain).outerjoin(BusinessDomain,BusinessDomain.business_id==Business.id)).all():
        existing_domain=indexed_domain or business_domain(existing)
        same_domain=bool(domain and existing_domain==domain)
        same_name=bool(len(name)>=3 and normalized_name(existing.name)==name)
        existing_location=normalized_name(existing.location)
        same_location=bool(location and existing_location and location==existing_location)
        reasons=[]
        if same_domain: reasons.append('same_domain')
        if same_name and (not location or not existing_location or same_location): reasons.append('same_name_and_compatible_location')
        if reasons:
            # This is an exact match on provided fields, not proof of legal identity.
            classification='exact_fields' if same_domain and same_name and same_location else 'possible'
            matches.append({'business_id':existing.id,'name':existing.name,'domain':existing_domain,'location':existing.location,'reasons':reasons,'classification':classification})
    return matches

def create_review(item, matches, session):
    data = item.model_dump() if hasattr(item, 'model_dump') else item.__dict__
    review=DuplicateReview(incoming=json.dumps(data,ensure_ascii=False),matches=json.dumps(matches,ensure_ascii=False),status='pending')
    session.add(review); session.flush(); return review

def add_source(session,business_id,source,kind,candidate_id=None,review_id=None):
    session.add(BusinessSource(business_id=business_id,source=source.strip() or 'Manual import',kind=kind,candidate_id=candidate_id,review_id=review_id))

def insert_lead(item, session, review_matches=True, source_kind='manual', candidate_id=None, review_id=None):
    name=item.name.strip()
    if not name: raise HTTPException(422,'Business name is required')
    url,domain=normalize_url(item.website)
    # A database row lock serializes matching and creation across worker processes.
    locked=session.execute(update(IdentityGuard).where(IdentityGuard.id=='global').values(counter=IdentityGuard.counter))
    if locked.rowcount!=1: raise RuntimeError('Identity guard is missing; run the database migration')
    if review_matches:
        matches=candidate_matches(item,domain,session)
        if matches: return None,create_review(item,matches,session)
    # The legacy unique field is deliberately unused for NEW records. Domain links
    # live in the non-unique business_domains table; existing values are untouched.
    b=Business(name=name,website=url,domain=None,industry=item.industry.strip(),location=item.location.strip(),source=item.source.strip() or 'Manual import')
    with session.begin_nested():
        session.add(b); session.flush()
        if domain: session.add(BusinessDomain(business_id=b.id,domain=domain))
        add_source(session,b.id,item.source,source_kind,candidate_id,review_id)
        session.flush()
    return b,None

def review_payload(r):
    try:
        incoming=json.loads(r.incoming); matches=json.loads(r.matches)
        if not isinstance(incoming,dict) or not isinstance(matches,list): raise ValueError()
        for m in matches:
            if not isinstance(m,dict) or not isinstance(m.get('business_id'),str) or not isinstance(m.get('name'),str) or not isinstance(m.get('reasons'),list) or not all(isinstance(reason,str) for reason in m['reasons']): raise ValueError()
            if m.get('domain') is not None and not isinstance(m['domain'],str): raise ValueError()
        LeadIn(**incoming)
        return incoming,matches,False
    except (ValueError,TypeError):
        return {'name':'Unreadable legacy candidate','website':'','location':'','industry':'','source':''},[],True

def serialize_review(r,session):
    incoming,matches,unreadable=review_payload(r)
    events=session.scalars(select(ReviewResolution).where(ReviewResolution.review_id==r.id).order_by(ReviewResolution.created_at,ReviewResolution.id)).all()
    resolution=events[-1] if events else None
    return {'id':r.id,'incoming':incoming,'matches':matches,'unreadable':unreadable,'raw_incoming':r.incoming if unreadable else None,'raw_matches':r.matches if unreadable else None,'classification':'exact_fields' if any(m.get('classification')=='exact_fields' for m in matches) else 'possible','status':r.status,'created_at':r.created_at.isoformat(),'resolved_at':r.resolved_at.isoformat() if r.resolved_at else None,'resolution':{'decision':resolution.decision,'matched_business_id':resolution.matched_business_id,'result_business_id':resolution.result_business_id} if resolution else None,'resolution_history':[{'decision':e.decision,'matched_business_id':e.matched_business_id,'result_business_id':e.result_business_id,'created_at':e.created_at.isoformat()} for e in events]}

@app.get('/api/duplicate-reviews', dependencies=[Depends(auth)])
def duplicate_reviews(session:Session=Depends(db)):
    return [serialize_review(r,session) for r in session.scalars(select(DuplicateReview).order_by(DuplicateReview.created_at.desc())).all()]

def add_review_event(session,review_id,decision,matched_business_id=None,result_business_id=None):
    last=session.scalar(select(ReviewResolution.created_at).where(ReviewResolution.review_id==review_id).order_by(ReviewResolution.created_at.desc()).limit(1))
    stamp=now()
    if last:
        if last.tzinfo is None: last=last.replace(tzinfo=timezone.utc)
        if stamp<=last: stamp=last+timedelta(microseconds=1)
    session.add(ReviewResolution(review_id=review_id,decision=decision,matched_business_id=matched_business_id,result_business_id=result_business_id,created_at=stamp))

@app.post('/api/duplicate-reviews/{review_id}/resolve', dependencies=[Depends(auth)])
def resolve_duplicate(review_id:str, action:ReviewAction, session:Session=Depends(db)):
    aliases={'keep_separate':'separate_business'}
    decision=aliases.get(action.decision,action.decision)
    statuses={'same_business':'duplicate','separate_business':'kept_separate','separate_branch':'branch','subsidiary':'subsidiary','parent_company':'parent_company','reviewed':'reviewed'}
    if decision not in statuses: raise HTTPException(422,'Invalid review decision')
    review=session.get(DuplicateReview,review_id)
    if not review: raise HTTPException(404,'Review not found')
    incoming,matches,unreadable=review_payload(review)
    if unreadable: raise HTTPException(422,'This legacy review is unreadable; its original data is retained for manual recovery')
    matched_ids={m.get('business_id') for m in matches if isinstance(m,dict)}
    target=action.matched_business_id
    if decision in ('same_business','separate_branch','subsidiary','parent_company'):
        if not target or target not in matched_ids: raise HTTPException(422,'Select a matching existing business for this decision')
        if not session.get(Business,target): raise HTTPException(409,'The selected existing business is no longer available')
    elif target and target not in matched_ids: raise HTTPException(422,'Selected business was not in the review matches')
    claimed=session.execute(update(DuplicateReview).where(DuplicateReview.id==review_id,DuplicateReview.status=='pending').values(status=statuses[decision],resolved_at=now()))
    if claimed.rowcount != 1: raise HTTPException(409,'This review has already been resolved')
    item=LeadIn(**incoming)
    candidate=session.scalar(select(ImportCandidate).where(ImportCandidate.review_id==review_id))
    result_id=None
    if decision=='same_business':
        result_id=target
        add_source(session,target,item.source,'review_duplicate',candidate.id if candidate else None,review_id)
    elif decision!='reviewed':
        business,_=insert_lead(item,session,review_matches=False,source_kind='review',candidate_id=candidate.id if candidate else None,review_id=review_id)
        result_id=business.id
        if decision in ('separate_branch','subsidiary','parent_company'):
            subject=target if decision=='parent_company' else result_id
            related=result_id if decision=='parent_company' else target
            relation='branch_of' if decision=='separate_branch' else 'subsidiary_of'
            session.add(BusinessRelationship(subject_business_id=subject,related_business_id=related,relation=relation,review_id=review_id))
    if candidate:
        candidate.status='resolved_'+decision
        candidate.business_id=result_id
    add_review_event(session,review_id,decision,target,result_id)
    session.commit(); session.refresh(review); return serialize_review(review,session)

@app.post('/api/duplicate-reviews/{review_id}/reopen', dependencies=[Depends(auth)])
def reopen_review(review_id:str,session:Session=Depends(db)):
    # Legacy 'reviewed' meant no decision. Preserve all previous decision events.
    changed=session.execute(update(DuplicateReview).where(DuplicateReview.id==review_id,DuplicateReview.status=='reviewed').values(status='pending',resolved_at=None))
    if changed.rowcount!=1:
        if not session.get(DuplicateReview,review_id): raise HTTPException(404,'Review not found')
        raise HTTPException(409,'Only a review marked reviewed without a decision can be reopened')
    add_review_event(session,review_id,'reopen')
    session.commit(); review=session.get(DuplicateReview,review_id); return serialize_review(review,session)

@app.get('/api/leads/{lead_id}/sources', dependencies=[Depends(auth)])
def lead_sources(lead_id:str,session:Session=Depends(db)):
    if not session.get(Business,lead_id): raise HTTPException(404,'Lead not found')
    rows=session.scalars(select(BusinessSource).where(BusinessSource.business_id==lead_id).order_by(BusinessSource.created_at)).all()
    return [{'id':x.id,'source':x.source,'kind':x.kind,'candidate_id':x.candidate_id,'review_id':x.review_id,'created_at':x.created_at.isoformat()} for x in rows]

@app.get('/api/leads/{lead_id}/relationships', dependencies=[Depends(auth)])
def lead_relationships(lead_id:str,session:Session=Depends(db)):
    if not session.get(Business,lead_id): raise HTTPException(404,'Lead not found')
    rows=session.scalars(select(BusinessRelationship).where((BusinessRelationship.subject_business_id==lead_id)|(BusinessRelationship.related_business_id==lead_id))).all()
    return [{'id':x.id,'subject_business_id':x.subject_business_id,'related_business_id':x.related_business_id,'relation':x.relation,'review_id':x.review_id,'created_at':x.created_at.isoformat()} for x in rows]

@app.get('/api/import-batches', dependencies=[Depends(auth)])
def list_imports(session:Session=Depends(db)):
    return [{'id':x.id,'created_at':x.created_at.isoformat()} for x in session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc())).all()]

@app.get('/api/import-batches/{batch_id}', dependencies=[Depends(auth)])
def import_details(batch_id:str,session:Session=Depends(db)):
    batch=session.get(ImportBatch,batch_id)
    if not batch: raise HTTPException(404,'Import batch not found')
    rows=session.scalars(select(ImportCandidate).where(ImportCandidate.batch_id==batch_id).order_by(ImportCandidate.row_number)).all()
    return {'id':batch.id,'created_at':batch.created_at.isoformat(),'original_csv':batch.original_csv,'candidates':[{'id':x.id,'row_number':x.row_number,'raw_data':json.loads(x.raw_data),'status':x.status,'business_id':x.business_id,'review_id':x.review_id,'error':x.error} for x in rows]}


@app.get('/health')
def health(): return {'status':'ok','sending_enabled':False}
@app.get('/api/session', dependencies=[Depends(auth)])
def session_status(): return {'authenticated':True}
@app.get('/api/leads', dependencies=[Depends(auth)])
def leads(offset:int=Query(0,ge=0),limit:int=Query(500,ge=1,le=1000),has_website:Optional[bool]=Query(None),session:Session=Depends(db)):
    stmt = select(Business)
    if has_website is True:
        stmt = stmt.where(Business.website.isnot(None), Business.website != '')
    elif has_website is False:
        stmt = stmt.where(or_(Business.website.is_(None), Business.website == ''))
    return [serialize(x) for x in session.scalars(stmt.order_by(Business.created_at.desc(),Business.id).offset(offset).limit(limit)).all()]
@app.post('/api/leads', dependencies=[Depends(auth)])
def add_lead(item:LeadIn, session:Session=Depends(db)):
    b,review=insert_lead(item,session)
    session.commit()
    if review: return {'status':'review','review':serialize_review(review,session)}
    return serialize(b)
@app.post('/api/import', dependencies=[Depends(auth)])
def import_csv(item:ImportIn, session:Session=Depends(db)):
    reader=csv.DictReader(io.StringIO(item.csv_text.lstrip('\ufeff'),newline=''),strict=True)
    try: fieldnames=reader.fieldnames
    except csv.Error: raise HTTPException(422,'Malformed CSV; check quotes and delimiters')
    if not fieldnames: raise HTTPException(422, 'CSV requires a name column')
    headers=[x.strip().lower() for x in fieldnames]
    if 'name' not in headers: raise HTTPException(422, 'CSV requires a name column')
    if len(headers)!=len(set(headers)): raise HTTPException(422, 'CSV contains duplicate column names')
    try: rows=list(reader)
    except csv.Error: raise HTTPException(422,'Malformed CSV; check quotes and delimiters')
    if len(rows)>500: raise HTTPException(422,'Import exceeds 500 rows; split the CSV into smaller batches. No rows were imported.')
    batch=ImportBatch(original_csv=item.csv_text); session.add(batch); session.flush()
    added=duplicates=0; errors=[]
    for rowno,raw in enumerate(rows,2):
        candidate=ImportCandidate(batch_id=batch.id,row_number=rowno,raw_data=json.dumps(raw,ensure_ascii=False),status='invalid',error='')
        session.add(candidate); session.flush()
        if None in raw:
            candidate.error='Too many fields'; errors.append(f'Row {rowno}: {candidate.error}'); continue
        row={str(k).strip().lower(): (v or '').strip() for k,v in raw.items() if k is not None and isinstance(v,str)}
        if not any(row.values()):
            candidate.error='Empty row'; errors.append(f'Row {rowno}: {candidate.error}'); continue
        try:
            lead=LeadIn(name=row.get('name',''),website=row.get('website',''),industry=row.get('industry',''),location=row.get('location',''),source=row.get('source') or 'CSV import')
            business,review=insert_lead(lead,session,source_kind='csv',candidate_id=candidate.id)
            if business:
                candidate.status='added'; candidate.business_id=business.id; added+=1
            else:
                candidate.status='review'; candidate.review_id=review.id; duplicates+=1
        except (ValueError,HTTPException) as e:
            candidate.error=str(getattr(e,'detail',e))[:180]; errors.append(f'Row {rowno}: {candidate.error}')
    session.commit(); return {'batch_id':batch.id,'added':added,'duplicates':duplicates,'errors':errors}

_research_slots=threading.BoundedSemaphore(2)
def fetch_public_page(url):
    return run_crawl(url,DATABASE_URL)

def analyze_html(url, html):
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True)[:250] if soup.title else ''
    meta=soup.find('meta',attrs={'name':re.compile('^description$',re.I)})
    description=(meta.get('content','') if meta else '')[:500]
    viewport=bool(soup.find('meta',attrs={'name':re.compile('^viewport$',re.I)}))
    stamp=now().isoformat()
    evidence=[{'fact':'Fetched page responded with HTML','url':url,'collected_at':stamp,'confidence':'high'}, {'fact':('Viewport meta tag present' if viewport else 'No viewport meta tag found in fetched HTML'),'url':url,'collected_at':stamp,'confidence':'high'}]
    if title: evidence.append({'fact':'Page title: '+title,'url':url,'collected_at':stamp,'confidence':'high'})
    # These are triage signals, not assertions about purchasing intent or a full audit.
    return {'title':title,'description':description,'evidence':evidence,'opportunities':[
        {'service':'Website development','score':None,'confidence':'unknown','reason':'Website needs are unknown. Review the technical observations; a viewport tag alone does not establish a service opportunity.','evidence_indexes':[1]},
        {'service':'E-commerce development','score':None,'confidence':'unknown','reason':'Insufficient evidence to assess e-commerce needs.','evidence_indexes':[]},
        {'service':'CRM / business automation','score':None,'confidence':'unknown','reason':'Internal workflows cannot be assessed from the homepage alone.','evidence_indexes':[]}
    ],'business_quality':None,'conversion_potential':None,'evidence_confidence':'limited','limitations':'Observed page characteristics only. Service needs, intent, budget and conversion potential are unknown without supporting evidence.'}

@app.post('/api/leads/{lead_id}/research', dependencies=[Depends(auth)])
def research(lead_id:str, session:Session=Depends(db)):
    b=session.get(Business,lead_id)
    if not b: raise HTTPException(404,'Lead not found')
    if not b.website: raise HTTPException(400,'Add a website before researching')
    if not _research_slots.acquire(blocking=False): raise HTTPException(429,'Research capacity is busy; retry later')
    try:
        try: url,html=fetch_public_page(b.website); report=analyze_html(url,html)
        except CrawlCapacity: raise HTTPException(429,'Research capacity is busy; retry later')
        except CrawlTimeout: raise HTTPException(504,'Research exceeded the total deadline')
        except (CrawlFailure,OSError,ValueError):
            raise HTTPException(422, 'Research did not complete. Check site access, robots.txt, URL and network settings.')
    finally: _research_slots.release()
    b.report=json.dumps(report); b.researched_at=now(); session.add(ResearchHistory(business_id=b.id,report=b.report,collected_at=b.researched_at,kind='observed'))
    try:
        qual_data = QualificationEngine.analyze(url, html, b.name)
        session.add(LeadQualification(
            business_id=b.id,
            business_quality_score=qual_data.get('business_quality') or 0,
            conversion_potential_score=qual_data.get('conversion_potential') or 0,
            evidence_confidence=qual_data.get('evidence_confidence') or 'low',
            service_scores_json=json.dumps(qual_data.get('opportunities', [])),
            missing_information_json=json.dumps(qual_data.get('missing_information', [])),
            ai_summary=qual_data.get('ai_summary', ''),
            created_at=now()
        ))
        observed_contacts = QualificationEngine.extract_public_contacts(url, html, b.name)
        if observed_contacts:
            from .contacts.contact_service import ContactService
            ContactService(session).save_observed_contacts(b.id, observed_contacts)
    except Exception:
        pass
    session.commit()
    return serialize(b)
@app.get('/api/leads/{lead_id}/research-history', dependencies=[Depends(auth)])
def research_history(lead_id:str, session:Session=Depends(db)):
    if not session.get(Business,lead_id): raise HTTPException(404,'Lead not found')
    rows=session.scalars(select(ResearchHistory).where(ResearchHistory.business_id==lead_id).order_by(ResearchHistory.collected_at.desc())).all()
    return [{'id':r.id,'collected_at':r.collected_at.isoformat(),'kind':r.kind,'report':presentation_report(r.report),'unreadable_legacy':bool(r.report and not presentation_report(r.report))} for r in rows]

@app.get('/api/export.csv', dependencies=[Depends(auth)])
def export(session:Session=Depends(db)):
    f=io.StringIO(newline=''); w=csv.writer(f); w.writerow(['business_id','name','website','industry','location','source','researched_at','website_opportunity_score'])
    def safe(v):
        s='' if v is None else str(v); return "'"+s if s.startswith(('\t','\r','\n')) or s.lstrip().startswith(('=','+','-','@')) else s
    for b in session.scalars(select(Business).order_by(Business.created_at.desc())).all():
        report=presentation_report(b.report) or {}; ops=report.get('opportunities',[])
        w.writerow([safe(x) for x in [b.id,b.name,b.website,b.industry,b.location,b.source,b.researched_at.isoformat() if b.researched_at else '',ops[0]['score'] if ops else '']])
    return Response(f.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="sparkxflow-leads.csv"'})

from .api_router import router as extended_router, get_db as router_db
app.dependency_overrides[router_db] = db
app.include_router(extended_router, prefix='/api', dependencies=[Depends(auth)])

static=ROOT/'frontend'/'dist'
if static.exists():
    app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')
    @app.get('/')
    def index(): return FileResponse(static/'index.html')
