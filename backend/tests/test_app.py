import os
os.environ['ADMIN_TOKEN']='test-admin-token-very-long-and-safe'
os.environ['DATABASE_URL']='sqlite://'
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.engine import URL
from app import main, crawler
# Each test gets a private SQLite database; no test depends on execution order.
client=TestClient(main.app,base_url='http://localhost',client=('127.0.0.1',50000))
headers={'Authorization':'Bearer '+os.environ['ADMIN_TOKEN']}

class NoPacing:
    @__import__('contextlib').contextmanager
    def host_permit(self,host,deadline): yield
    def pace(self,host,deadline): pass
    def defer(self,host,seconds): pass

@pytest.fixture(autouse=True)
def isolated_database(tmp_path):
    old_engine=main.engine
    engine=main.create_engine(URL.create('sqlite',database=(tmp_path/'api-test.db').as_posix()),connect_args={'check_same_thread':False})
    main.engine=engine; main.SessionLocal.configure(bind=engine)
    main.Base.metadata.create_all(engine)
    with main.SessionLocal() as session:
        session.add(main.IdentityGuard(id='global',counter=0)); session.add(main.CrawlerControl(id='global',counter=0)); session.commit()
    main._auth_failures.clear()
    yield
    main._auth_failures.clear()
    engine.dispose(); main.engine=old_engine; main.SessionLocal.configure(bind=old_engine)

def test_auth_and_no_sending():
    assert client.get('/api/leads').status_code==401
    assert client.post('/api/outreach/anything/send',headers=headers).status_code==404

def test_import_dedup_and_export():
    r=client.post('/api/import',headers=headers,json={'csv_text':'name,website,industry\nExample,https://www.example.com,Software\nDuplicate,https://example.com,Software\n'})
    assert r.status_code==200 and r.json()['added']==1 and r.json()['duplicates']==1
    assert 'Example' in client.get('/api/export.csv',headers=headers).text

def test_invalid_and_public_restrictions():
    assert client.post('/api/leads',headers=headers,json={'name':'x','website':'http://example.com:8080'}).status_code==422
    with pytest.raises(crawler.CrawlBlocked,match='public IP'):
        crawler.checked_request('http://127.0.0.1/',NoPacing(),__import__('time').monotonic()+5)

def test_evidence_and_unknowns():
    r=main.analyze_html('https://example.com/','<html><title>Test</title><body>Hello</body></html>')
    assert r['opportunities'][0]['score'] is None and r['opportunities'][1]['score'] is None
    assert r['evidence'][1]['url']=='https://example.com/'

def test_research_robots(monkeypatch):
    def fake(url,coordinator,deadline):
        if url.endswith('/robots.txt'): return 200,{},b'User-agent: *\nDisallow: /private'
        return 200,{'Content-Type':'text/html'},b'<title>Hello</title>'
    monkeypatch.setattr(crawler,'checked_request',fake)
    try: crawler.fetch_public_page('https://example.com/private',NoPacing(),__import__('time').monotonic()+5)
    except crawler.CrawlBlocked as e: assert 'disallows' in str(e)
    else: assert False

def test_duplicate_review_preserves_incoming():
    first=client.post('/api/leads',headers=headers,json={'name':'Unique Bakery','website':'https://bakery-example.test','location':'York'})
    assert first.status_code==200
    second=client.post('/api/leads',headers=headers,json={'name':'UNIQUE BAKERY','website':'https://second-bakery-example.test','location':'York'})
    assert second.json()['status']=='review'
    review=second.json()['review']
    assert review['incoming']['name']=='UNIQUE BAKERY'
    assert client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'keep_separate'}).status_code==200
    assert len([x for x in client.get('/api/leads',headers=headers).json() if 'bakery' in x['name'].lower()])==2

def test_same_domain_review_can_be_kept_separate():
    original=client.post('/api/leads',headers=headers,json={'name':'Example Inc','website':'https://example.com','location':'London'}).json()
    result=client.post('/api/leads',headers=headers,json={'name':'Different operation','website':'https://example.com','location':'Leeds'})
    review=result.json()['review']
    assert review['classification']=='possible'
    resolved=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'separate_business'})
    assert resolved.status_code==200
    leads=client.get('/api/leads',headers=headers).json()
    assert len(leads)==2 and all(x['domain']=='example.com' for x in leads)
    assert original['id'] in {x['id'] for x in leads}
    assert any(x['id']==review['id'] and x['status']=='kept_separate' for x in client.get('/api/duplicate-reviews',headers=headers).json())

def test_csv_validation_and_500_row_limit():
    duplicate_header=client.post('/api/import',headers=headers,json={'csv_text':'name, Name\na,b'})
    assert duplicate_header.status_code==422
    lines='name\n'+''.join('Batch entry '+str(i)+'\n' for i in range(501))
    result=client.post('/api/import',headers=headers,json={'csv_text':lines})
    assert result.status_code==422 and '500 rows' in result.json()['detail']
    assert client.get('/api/leads',headers=headers).json()==[]
    assert client.get('/api/import-batches',headers=headers).json()==[]

def test_research_history_keeps_each_report(monkeypatch):
    created=client.post('/api/leads',headers=headers,json={'name':'Research history company','website':'https://research-history.example'})
    lead_id=created.json()['id']
    monkeypatch.setattr(main,'fetch_public_page',lambda url:(url,'<html><title>First</title></html>'))
    one=client.post('/api/leads/'+lead_id+'/research',headers=headers)
    assert one.status_code==200 and one.json()['report']['opportunities'][0]['score'] is None
    monkeypatch.setattr(main,'fetch_public_page',lambda url:(url,'<html><title>Second</title></html>'))
    assert client.post('/api/leads/'+lead_id+'/research',headers=headers).status_code==200
    rows=client.get('/api/leads/'+lead_id+'/research-history',headers=headers).json()
    assert len(rows)==2 and {r['report']['title'] for r in rows}=={'First','Second'}
    assert all(r['report']['opportunities'][0]['score'] is None for r in rows)

def test_legacy_invalid_and_numeric_reports_are_not_deleted():
    assert main.presentation_report('not valid json') is None
    raw='{"evidence":[],"opportunities":[{"service":"Website development","score":45,"reason":"need","confidence":"high"}]}'
    clean=main.presentation_report(raw)
    assert clean['opportunities'][0]['score'] is None and clean['opportunities'][0]['confidence']=='unknown'
    assert '45' in raw

def test_local_only_rejects_remote_peer_bad_host_and_bad_origin():
    remote=TestClient(main.app,base_url='http://localhost',client=('192.0.2.10',50000))
    assert remote.get('/health').status_code==403
    assert client.get('/health',headers={'host':'attacker.example'}).status_code==403
    assert client.post('/api/leads',headers={**headers,'origin':'https://attacker.example'},json={'name':'Nope'}).status_code==403
    assert client.get('/health').status_code==200

def test_research_capacity_limit(monkeypatch):
    assert main._research_slots.acquire(False)
    assert main._research_slots.acquire(False)
    try:
        lead=client.post('/api/leads',headers=headers,json={'name':'Capacity test','website':'https://capacity.example'}).json()
        assert client.post('/api/leads/'+lead['id']+'/research',headers=headers).status_code==429
    finally:
        main._research_slots.release(); main._research_slots.release()

def test_bad_url_schemes_and_bad_hosts_rejected():
    for url in ['ftp://example.com','https://bad host/','https://-bad.example','https://example.com/\nfoo']:
        assert client.post('/api/leads',headers=headers,json={'name':'URL validation','website':url}).status_code==422

def test_bad_csv_and_spreadsheet_formula_export():
    assert client.post('/api/import',headers=headers,json={'csv_text':'name,website\n"unfinished,https://example.com'}).status_code==422
    assert client.post('/api/leads',headers=headers,json={'name':'=2+2'}).status_code==200
    csv_text=client.get('/api/export.csv',headers=headers).text
    assert "'=2+2" in csv_text

def test_paginated_leads_and_session():
    for i in range(4): assert client.post('/api/leads',headers=headers,json={'name':f'Pagination business {i}'}).status_code==200
    assert client.get('/api/session',headers=headers).json()=={'authenticated':True}
    p1=client.get('/api/leads?offset=0&limit=2',headers=headers).json()
    p2=client.get('/api/leads?offset=2&limit=2',headers=headers).json()
    assert len(p1)==2 and len(p2)==2 and {x['id'] for x in p1}.isdisjoint(x['id'] for x in p2)
    assert client.get('/api/leads?limit=1001',headers=headers).status_code==422

def test_research_blocks_mixed_public_and_private_dns(monkeypatch):
    monkeypatch.setattr(crawler.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))])
    import pytest
    with pytest.raises(crawler.CrawlBlocked,match='public IP'): crawler.checked_request('https://test.example/',NoPacing(),__import__('time').monotonic()+5)

def test_robots_failure_stops_research(monkeypatch):
    monkeypatch.setattr(crawler,'checked_request',lambda url,coordinator,deadline:(503,{},b''))
    import pytest
    with pytest.raises(crawler.CrawlBlocked,match='robots.txt'): crawler.fetch_public_page('https://test.example/',NoPacing(),__import__('time').monotonic()+5)

def test_auth_rate_limit_and_reset():
    main._auth_failures.clear()
    try:
        for _ in range(10): assert client.get('/api/session',headers={'Authorization':'Bearer wrong'}).status_code==401
        assert client.get('/api/session',headers=headers).status_code==429
    finally: main._auth_failures.clear()

def test_invalid_csv_header_is_422():
    assert client.post('/api/import',headers=headers,json={'csv_text':'"unclosed header'}).status_code==422

def test_research_redirect_checks_robots_for_each_origin(monkeypatch):
    visited=[]
    def fake(url,coordinator,deadline):
        visited.append(url)
        if url.endswith('/robots.txt'): return 404,{},b''
        if 'first.example' in url: return 302,{'Location':'https://second.example/page'},b''
        return 200,{'Content-Type':'text/html; charset=iso-8859-1'},b'<title>caf\xe9</title>'
    monkeypatch.setattr(crawler,'checked_request',fake)
    url,html=crawler.fetch_public_page('https://first.example/',NoPacing(),__import__('time').monotonic()+5)
    assert url=='https://second.example/page' and 'café' in html
    assert visited==['https://first.example/robots.txt','https://first.example/','https://second.example/robots.txt','https://second.example/page']

def test_research_errors_do_not_expose_raw_exceptions(monkeypatch):
    lead=client.post('/api/leads',headers=headers,json={'name':'Error handling test','website':'https://error-handling.example'}).json()
    def fail(url): raise OSError('secret-diagnostic-information')
    monkeypatch.setattr(main,'fetch_public_page',fail)
    response=client.post('/api/leads/'+lead['id']+'/research',headers=headers)
    assert response.status_code==422 and 'secret-diagnostic-information' not in response.text

def test_response_includes_request_id_without_logging_token(caplog):
    with caplog.at_level('INFO',logger='sparkxflow'):
        response=client.get('/api/session',headers=headers)
    assert response.headers.get('x-request-id')
    assert os.environ['ADMIN_TOKEN'] not in caplog.text

def test_mark_reviewed_preserves_original_record_and_does_not_merge():
    first=client.post('/api/leads',headers=headers,json={'name':'Review retention company','location':'York'}).json()
    incoming={'name':'REVIEW RETENTION COMPANY','location':'York','industry':'Retail','source':'Sample directory'}
    review=client.post('/api/leads',headers=headers,json=incoming).json()['review']
    resolved=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'reviewed'})
    assert resolved.status_code==200
    retained=next(x for x in client.get('/api/duplicate-reviews',headers=headers).json() if x['id']==review['id'])
    assert retained['incoming']['industry']=='Retail' and retained['incoming']['source']=='Sample directory'
    assert retained['matches'][0]['business_id']==first['id'] and retained['status']=='reviewed'
    assert len(client.get('/api/leads',headers=headers).json())==1
    assert client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'keep_separate'}).status_code==409

def test_concurrent_review_resolution_is_atomic():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    assert client.post('/api/leads',headers=headers,json={'name':'Concurrent Company'}).status_code==200
    review=client.post('/api/leads',headers=headers,json={'name':'CONCURRENT COMPANY'}).json()['review']
    barrier=Barrier(2)
    def resolve(_):
        barrier.wait(timeout=10)
        return client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'keep_separate'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(resolve,range(2)))
    assert sorted(results)==[200,409]
    assert len(client.get('/api/leads',headers=headers).json())==2
    saved=next(x for x in client.get('/api/duplicate-reviews',headers=headers).json() if x['id']==review['id'])
    assert saved['status']=='kept_separate' and saved['incoming']['name']=='CONCURRENT COMPANY'

def test_exact_fields_match_is_reviewed_not_automatically_merged():
    original=client.post('/api/leads',headers=headers,json={'name':'Acme Cafe','website':'https://www.acme.example','location':'York','source':'Directory A'}).json()
    review=client.post('/api/leads',headers=headers,json={'name':'ACME CAFE','website':'https://acme.example','location':'York','source':'Directory B'}).json()['review']
    assert review['classification']=='exact_fields'
    assert len(client.get('/api/leads',headers=headers).json())==1
    assert client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'same_business'}).status_code==422
    result=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'same_business','matched_business_id':original['id']})
    assert result.status_code==200 and result.json()['resolution']['result_business_id']==original['id']
    saved=next(x for x in client.get('/api/duplicate-reviews',headers=headers).json() if x['id']==review['id'])
    assert saved['incoming']['source']=='Directory B' and saved['status']=='duplicate'
    sources=client.get('/api/leads/'+original['id']+'/sources',headers=headers).json()
    assert {x['source'] for x in sources}=={'Directory A','Directory B'}
    assert len(client.get('/api/leads',headers=headers).json())==1

def test_multiple_branches_sharing_domain_with_relationships():
    parent=client.post('/api/leads',headers=headers,json={'name':'Westside Clinic','website':'https://clinic.example','location':'London','source':'Official site'}).json()
    for city in ['Leeds','York']:
        candidate=client.post('/api/leads',headers=headers,json={'name':'Westside Clinic','website':'https://clinic.example','location':city,'source':'Local directory'}).json()['review']
        assert candidate['classification']=='possible'
        response=client.post('/api/duplicate-reviews/'+candidate['id']+'/resolve',headers=headers,json={'decision':'separate_branch','matched_business_id':parent['id']})
        assert response.status_code==200
        branch_id=response.json()['resolution']['result_business_id']
        relations=client.get('/api/leads/'+branch_id+'/relationships',headers=headers).json()
        assert relations[0]['subject_business_id']==branch_id and relations[0]['related_business_id']==parent['id'] and relations[0]['relation']=='branch_of'
    leads=client.get('/api/leads',headers=headers).json()
    assert len(leads)==3 and {x['location'] for x in leads}=={'London','Leeds','York'}
    assert {x['domain'] for x in leads}=={'clinic.example'}
    assert len(client.get('/api/leads/'+parent['id']+'/relationships',headers=headers).json())==2

@pytest.mark.parametrize(('decision','new_is_subject'),[('subsidiary',True),('parent_company',False)])
def test_parent_subsidiary_direction_is_explicit(decision,new_is_subject):
    existing=client.post('/api/leads',headers=headers,json={'name':'Existing Company','website':'https://group.example'}).json()
    review=client.post('/api/leads',headers=headers,json={'name':'Related Company','website':'https://group.example'}).json()['review']
    response=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':decision,'matched_business_id':existing['id']})
    assert response.status_code==200
    new_id=response.json()['resolution']['result_business_id']
    rel=client.get('/api/leads/'+new_id+'/relationships',headers=headers).json()[0]
    assert rel['relation']=='subsidiary_of'
    assert rel['subject_business_id']==(new_id if new_is_subject else existing['id'])
    assert rel['related_business_id']==(existing['id'] if new_is_subject else new_id)

def test_csv_preserves_every_candidate_source_and_decision():
    csv_text='name,website,location,source,extra\nCafe,https://cafe.example,York,Directory A,first\nCafe,https://cafe.example,York,Directory B,second\nBranch,https://cafe.example,Leeds,Directory C,third\n,https://missing.example,,,invalid\n'
    response=client.post('/api/import',headers=headers,json={'csv_text':csv_text})
    assert response.status_code==200
    result=response.json(); assert (result['added'],result['duplicates'])==(1,2)
    batch=client.get('/api/import-batches/'+result['batch_id'],headers=headers).json()
    assert batch['original_csv']==csv_text and len(batch['candidates'])==4
    assert [x['status'] for x in batch['candidates']]==['added','review','review','invalid']
    assert [x['raw_data']['extra'] for x in batch['candidates']]==['first','second','third','invalid']
    original=batch['candidates'][0]['business_id']
    exact=batch['candidates'][1]['review_id']
    branch=batch['candidates'][2]['review_id']
    assert client.post('/api/duplicate-reviews/'+exact+'/resolve',headers=headers,json={'decision':'same_business','matched_business_id':original}).status_code==200
    assert client.post('/api/duplicate-reviews/'+branch+'/resolve',headers=headers,json={'decision':'separate_branch','matched_business_id':original}).status_code==200
    after=client.get('/api/import-batches/'+result['batch_id'],headers=headers).json()
    assert [x['status'] for x in after['candidates']]==['added','resolved_same_business','resolved_separate_branch','invalid']
    assert after['candidates'][1]['business_id']==original and after['candidates'][1]['raw_data']['source']=='Directory B'
    assert {x['source'] for x in client.get('/api/leads/'+original+'/sources',headers=headers).json()}=={'Directory A','Directory B'}

def test_review_target_must_be_a_matched_business_and_failure_retains_candidate():
    original=client.post('/api/leads',headers=headers,json={'name':'Alpha','website':'https://alpha.example'}).json()
    other=client.post('/api/leads',headers=headers,json={'name':'Unrelated'}).json()
    review=client.post('/api/leads',headers=headers,json={'name':'Alpha branch','website':'https://alpha.example'}).json()['review']
    r=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'separate_branch','matched_business_id':other['id']})
    assert r.status_code==422
    retained=next(x for x in client.get('/api/duplicate-reviews',headers=headers).json() if x['id']==review['id'])
    assert retained['status']=='pending' and retained['matches'][0]['business_id']==original['id']

def test_concurrent_imports_do_not_bypass_duplicate_review():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier=Barrier(2)
    payload={'name':'Concurrent Clinic','website':'https://concurrent.example','location':'York'}
    def submit(_):
        barrier.wait(timeout=10)
        return client.post('/api/leads',headers=headers,json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(submit,range(2)))
    assert all(r.status_code==200 for r in responses)
    assert sum(r.json().get('status')=='review' for r in responses)==1
    assert len(client.get('/api/leads',headers=headers).json())==1
    assert len(client.get('/api/duplicate-reviews',headers=headers).json())==1

def test_legacy_marked_reviewed_can_be_reopened_without_losing_history():
    existing=client.post('/api/leads',headers=headers,json={'name':'Legacy Shop','website':'https://legacy.example','location':'York'}).json()
    review=client.post('/api/leads',headers=headers,json={'name':'Legacy Shop','website':'https://legacy.example','location':'York'}).json()['review']
    assert client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'reviewed'}).status_code==200
    reopened=client.post('/api/duplicate-reviews/'+review['id']+'/reopen',headers=headers)
    assert reopened.status_code==200 and reopened.json()['status']=='pending'
    done=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'same_business','matched_business_id':existing['id']})
    assert done.status_code==200
    with main.SessionLocal() as session:
        events=session.scalars(main.select(main.ReviewResolution).where(main.ReviewResolution.review_id==review['id'])).all()
        assert {e.decision for e in events}=={'reviewed','reopen','same_business'}

def test_malformed_legacy_review_is_retained_and_does_not_break_listing():
    with main.SessionLocal() as session:
        review=main.DuplicateReview(incoming='broken incoming',matches='broken matches',status='pending')
        session.add(review);session.commit();review_id=review.id
    listed=client.get('/api/duplicate-reviews',headers=headers)
    assert listed.status_code==200 and listed.json()[0]['unreadable'] is True
    assert listed.json()[0]['raw_incoming']=='broken incoming'
    denied=client.post('/api/duplicate-reviews/'+review_id+'/resolve',headers=headers,json={'decision':'separate_business'})
    assert denied.status_code==422
    with main.SessionLocal() as session:
        saved=session.get(main.DuplicateReview,review_id)
        assert saved.incoming=='broken incoming' and saved.matches=='broken matches' and saved.status=='pending'

def test_csv_without_a_source_uses_csv_attribution():
    r=client.post('/api/import',headers=headers,json={'csv_text':'name,source\nAttribution test,\n'})
    assert r.status_code==200 and r.json()['added']==1
    lead=client.get('/api/leads',headers=headers).json()[0]
    source=client.get('/api/leads/'+lead['id']+'/sources',headers=headers).json()[0]
    assert lead['source']=='CSV import' and source['source']=='CSV import' and source['kind']=='csv'

def test_review_event_order_is_stable_even_if_clock_does_not_advance(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setattr(main,'now',lambda:datetime(2025,1,1,tzinfo=timezone.utc))
    existing=client.post('/api/leads',headers=headers,json={'name':'Clock Shop','website':'https://clock.example','location':'York'}).json()
    review=client.post('/api/leads',headers=headers,json={'name':'Clock Shop','website':'https://clock.example','location':'York'}).json()['review']
    assert client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'reviewed'}).status_code==200
    assert client.post('/api/duplicate-reviews/'+review['id']+'/reopen',headers=headers).status_code==200
    result=client.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'same_business','matched_business_id':existing['id']})
    assert result.status_code==200 and result.json()['resolution']['decision']=='same_business'
    assert [e['decision'] for e in result.json()['resolution_history']]==['reviewed','reopen','same_business']

def test_research_timeout_does_not_overwrite_evidence(monkeypatch):
    lead=client.post('/api/leads',headers=headers,json={'name':'Timeout Company','website':'https://timeout.example'}).json()
    monkeypatch.setattr(main,'fetch_public_page',lambda url:(url,'<title>First</title>'))
    assert client.post('/api/leads/'+lead['id']+'/research',headers=headers).status_code==200
    def timeout(url): raise main.CrawlTimeout('simulated DNS delay')
    monkeypatch.setattr(main,'fetch_public_page',timeout)
    result=client.post('/api/leads/'+lead['id']+'/research',headers=headers)
    assert result.status_code==504
    assert len(client.get('/api/leads/'+lead['id']+'/research-history',headers=headers).json())==1
