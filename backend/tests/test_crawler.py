"""Deterministic crawler safety tests; no real external website is contacted."""
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
import pytest
from sqlalchemy.engine import URL
from app.crawler import Coordinator, CrawlBusy, CrawlBlocked, CrawlDeadline, robots_rules, fetch_public_page
from app.crawl_client import run_crawl, CrawlTimeout

ROOT=Path(__file__).resolve().parents[2]

class NoDelay:
    @__import__('contextlib').contextmanager
    def host_permit(self,*args): yield
    def defer(self,*args): pass

@pytest.fixture
def database_url(tmp_path):
    path=tmp_path/'coordination.db'
    with closing(sqlite3.connect(path)) as c:
        c.executescript('''CREATE TABLE crawler_control(id VARCHAR(20) PRIMARY KEY,counter INTEGER NOT NULL);
        INSERT INTO crawler_control VALUES('global',0);
        CREATE TABLE crawler_leases(id VARCHAR(36) PRIMARY KEY,expires_at FLOAT NOT NULL);
        CREATE TABLE crawler_host_limits(host VARCHAR(253) PRIMARY KEY,next_allowed FLOAT NOT NULL,owner VARCHAR(36),active_until FLOAT NOT NULL);''')
        c.commit()
    return str(URL.create('sqlite',database=path.as_posix()))

def test_shared_database_limits_global_concurrency_and_releases(database_url):
    one,two,three=[Coordinator(database_url) for _ in range(3)]
    try:
        with one.lease(3),two.lease(3):
            with pytest.raises(CrawlBusy):
                with three.lease(3): pass
        with three.lease(3): pass
    finally:
        for c in (one,two,three): c.close()

def test_expired_crash_lease_is_recovered(database_url):
    from sqlalchemy import create_engine,text
    engine=create_engine(database_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO crawler_leases VALUES ('stale',:expiry)"),{'expiry':time.time()-1})
    worker=Coordinator(database_url)
    try:
        with worker.lease(1):
            with engine.connect() as c: assert c.execute(text("SELECT count(*) FROM crawler_leases WHERE id='stale'")).scalar_one()==0
    finally: worker.close();engine.dispose()

def test_host_pacing_survives_coordinator_restart(database_url):
    first=Coordinator(database_url,host_interval=0.35)
    second=Coordinator(database_url,host_interval=0.35)
    try:
        first.pace('one.example',time.monotonic()+3)
        first.close()
        start=time.monotonic()
        second.pace('one.example',time.monotonic()+3)
        assert time.monotonic()-start>=0.25
        # A different host is not forced to wait for the first host's reservation.
        start=time.monotonic();second.pace('other.example',time.monotonic()+3)
        assert time.monotonic()-start<0.3
    finally: second.close()

def test_pacing_respects_the_total_deadline(database_url):
    worker=Coordinator(database_url,host_interval=2)
    try:
        worker.pace('slow.example',time.monotonic()+2)
        with pytest.raises(CrawlDeadline): worker.pace('slow.example',time.monotonic()+0.1)
    finally: worker.close()

def test_two_separate_processes_share_concurrency_limit(database_url,tmp_path):
    script=tmp_path/'hold.py'
    script.write_text('''import os,sys,time\nfrom app.crawler import Coordinator\nc=Coordinator(os.environ["DATABASE_URL"])\nwith c.lease(30):\n open(sys.argv[1],"w").write("ready")\n until=time.monotonic()+25\n while not os.path.exists(sys.argv[2]) and time.monotonic()<until: time.sleep(.025)\nc.close()\n''',encoding='utf-8')
    env=os.environ.copy();env.update(DATABASE_URL=database_url,PYTHONPATH=str(ROOT/'backend'),PYTHONDONTWRITEBYTECODE='1')
    markers=[tmp_path/'worker-one',tmp_path/'worker-two']; release=tmp_path/'release';procs=[]
    try:
        for marker in markers:
            p=subprocess.Popen([sys.executable,str(script),str(marker),str(release)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            procs.append(p)
            until=time.monotonic()+8
            while not marker.exists() and p.poll() is None and time.monotonic()<until: time.sleep(.025)
            assert marker.exists(),f'worker did not acquire a lease: {p.stderr.read() if p.poll() is not None else "startup timed out"}'
        third=Coordinator(database_url)
        try:
            with pytest.raises(CrawlBusy):
                with third.lease(2): pass
        finally: third.close()
        release.write_text('release',encoding='utf-8')
        for p in procs:
            _,err=p.communicate(timeout=8);assert p.returncode==0,err
    finally:
        for p in procs:
            if p.poll() is None: p.kill();p.communicate(timeout=5)

def test_hard_deadline_terminates_actual_worker_with_blocked_dns(database_url,tmp_path):
    worker=ROOT/'backend/app/crawl_worker.py'
    marker=tmp_path/'dns-called'
    harness=tmp_path/'blocked_dns.py'
    harness.write_text(f'''import runpy,socket,sys,time\nsys.path.insert(0,{str(worker.parent)!r})\ndef blocked(*args,**kwargs):\n open({str(marker)!r},"w").write("called")\n time.sleep(30)\nsocket.getaddrinfo=blocked\nrunpy.run_path({str(worker)!r},run_name="__main__")\n''',encoding='utf-8')
    start=time.monotonic()
    with pytest.raises(CrawlTimeout): run_crawl('https://example.com/',database_url,deadline_seconds=4,worker_path=harness)
    assert marker.exists(), 'DNS mock was not reached'
    assert time.monotonic()-start<7

def test_robots_disallow_wildcards_and_allow_exceptions_are_conservative():
    body=b'User-agent: *\nDisallow: /private*\nAllow: /private/public\nCrawl-delay: 3\n'
    with pytest.raises(CrawlBlocked): robots_rules(body,'https://example.com/private/public')
    assert robots_rules(body,'https://example.com/about')==3
    with pytest.raises(CrawlBlocked): robots_rules(b'User-agent: *\nDisallow: /secret$\n','https://example.com/secret')

def test_robot_redirects_fail_closed(monkeypatch):
    from app import crawler
    class Stub:
        @__import__('contextlib').contextmanager
        def host_permit(self,*a): yield
        def defer(self,*a): pass
    calls=[]
    def fake(url,coordinator,deadline):
        calls.append(url);return 302,{'Location':'https://other.example/robots.txt'},b''
    monkeypatch.setattr(crawler,'checked_request',fake)
    with pytest.raises(CrawlBlocked,match='robots.txt'): fetch_public_page('https://example.com/',Stub(),time.monotonic()+3)
    assert calls==['https://example.com/robots.txt']

def test_https_to_http_redirect_is_rejected(monkeypatch):
    from app import crawler
    class Stub:
        @__import__('contextlib').contextmanager
        def host_permit(self,*a): yield
        def defer(self,*a): pass
    def fake(url,coordinator,deadline):
        if url.endswith('/robots.txt'): return 404,{},b''
        return 302,{'Location':'http://other.example/'},b''
    monkeypatch.setattr(crawler,'checked_request',fake)
    with pytest.raises(CrawlBlocked,match='downgrade'): fetch_public_page('https://example.com/',Stub(),time.monotonic()+3)

def test_robots_invalid_content_type_fails_closed(monkeypatch):
    from app import crawler
    monkeypatch.setattr(crawler,'checked_request',lambda *args:(200,{'Content-Type':'text/html'},b'<html>'))
    with pytest.raises(CrawlBlocked,match='content type'): fetch_public_page('https://example.com/',NoDelay(),time.monotonic()+3)

def test_two_separate_processes_share_per_host_pacing(database_url,tmp_path):
    script=tmp_path/'pace.py'
    script.write_text('''import os,time\nfrom app.crawler import Coordinator\nc=Coordinator(os.environ['DATABASE_URL'])\nc.pace('shared.example',time.monotonic()+10)\nprint(time.monotonic(),flush=True)\nc.close()\n''',encoding='utf-8')
    env=os.environ.copy();env.update(DATABASE_URL=database_url,PYTHONPATH=str(ROOT/'backend'),PYTHONDONTWRITEBYTECODE='1')
    procs=[subprocess.Popen([sys.executable,str(script)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    try:
        results=[]
        for p in procs:
            out,err=p.communicate(timeout=12);assert p.returncode==0,err;results.append(float(out.strip()))
        assert abs(results[1]-results[0])>=0.85
    finally:
        for p in procs:
            if p.poll() is None: p.kill();p.communicate(timeout=5)

def test_escaped_dollar_in_robots_rule_is_literal():
    with pytest.raises(CrawlBlocked):
        robots_rules(b'User-agent: *\nDisallow: /private%24\n','https://example.com/private%24')

def test_same_host_inflight_request_blocks_another_worker(database_url):
    first,second=Coordinator(database_url),Coordinator(database_url)
    try:
        with first.host_permit('shared.example',time.monotonic()+3):
            with pytest.raises(CrawlDeadline):
                with second.host_permit('shared.example',time.monotonic()+0.2): pass
    finally: first.close();second.close()

def test_robots_delay_is_applied_before_host_permit_is_released(database_url):
    first,second=Coordinator(database_url,host_interval=0.1),Coordinator(database_url,host_interval=0.1)
    try:
        with first.host_permit('delay.example',time.monotonic()+3): first.defer('delay.example',0.5)
        with pytest.raises(CrawlDeadline):
            with second.host_permit('delay.example',time.monotonic()+0.2): pass
    finally: first.close();second.close()

def test_worker_watchdog_exits_even_without_a_parent_timeout(database_url,tmp_path):
    import json
    worker=ROOT/'backend/app/crawl_worker.py'; marker=tmp_path/'watchdog-dns'
    harness=tmp_path/'orphan_dns.py'
    harness.write_text(f'''import runpy,socket,sys,time\nsys.path.insert(0,{str(worker.parent)!r})\ndef blocked(*args,**kwargs):\n open({str(marker)!r},"w").write("called")\n time.sleep(30)\nsocket.getaddrinfo=blocked\nrunpy.run_path({str(worker)!r},run_name="__main__")\n''',encoding='utf-8')
    env=os.environ.copy();env.update(DATABASE_URL=database_url,PYTHONDONTWRITEBYTECODE='1')
    proc=subprocess.Popen([sys.executable,str(harness)],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        _,err=proc.communicate(json.dumps({'url':'https://example.com/','deadline_seconds':3}),timeout=7)
        assert marker.exists(),'DNS mock was not reached'
        assert proc.returncode==124,err
    finally:
        if proc.poll() is None: proc.kill();proc.communicate(timeout=5)

def test_robots_request_rate_is_applied_conservatively():
    body=b'User-agent: *\nRequest-rate: 2/10\nCrawl-delay: 2\n'
    assert robots_rules(body,'https://example.com/')==5

def test_ambiguous_double_encoded_path_is_rejected():
    from app.crawler import target_parts
    with pytest.raises(CrawlBlocked): target_parts('https://example.com/%252e%252e/private')

def test_redirect_to_private_host_is_rechecked(monkeypatch):
    from app import crawler
    original=crawler.checked_request
    monkeypatch.setattr(crawler.socket,'getaddrinfo',lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))])
    def fake(url,coordinator,deadline):
        if url=='https://public.example/robots.txt': return 404,{},b''
        if url=='https://public.example/': return 302,{'Location':'https://127.0.0.1/private'},b''
        return original(url,coordinator,deadline)
    monkeypatch.setattr(crawler,'checked_request',fake)
    with pytest.raises(CrawlBlocked,match='public IP'):
        fetch_public_page('https://public.example/',NoDelay(),time.monotonic()+5)

def test_full_isolated_worker_success_uses_persistent_limiter(database_url,tmp_path):
    worker=ROOT/'backend/app/crawl_worker.py'; harness=tmp_path/'success.py'
    harness.write_text(f'''import runpy,sys\nsys.path.insert(0,{str(worker.parent)!r})\nimport crawler\ndef fake(url,coordinator,deadline):\n if url.endswith('/robots.txt'): return 200,{{'Content-Type':'text/plain'}},b'User-agent: *\\nDisallow: /private'\n return 200,{{'Content-Type':'text/html; charset=utf-8'}},b'<title>Dummy evidence</title>'\ncrawler.checked_request=fake\nrunpy.run_path({str(worker)!r},run_name='__main__')\n''',encoding='utf-8')
    url,html=run_crawl('https://example.com/',database_url,deadline_seconds=6,worker_path=harness)
    assert url=='https://example.com/' and 'Dummy evidence' in html
    from sqlalchemy import create_engine,text
    engine=create_engine(database_url)
    try:
        with engine.connect() as c:
            assert c.execute(text('SELECT count(*) FROM crawler_host_limits WHERE host=:host'),{'host':'example.com'}).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM crawler_leases')).scalar_one()==0
    finally:engine.dispose()

def test_special_translation_addresses_are_not_fetched():
    from app.crawler import is_public_ip
    assert is_public_ip('8.8.8.8')
    for address in ('127.0.0.1','192.0.0.9','::ffff:8.8.8.8','64:ff9b::7f00:1','2002:0808:0808::1'):
        assert not is_public_ip(address)

def test_versioned_user_agent_robots_rule_is_honored():
    with pytest.raises(CrawlBlocked):
        robots_rules(b'User-agent: SparkXFlowResearchBot/0.1\nDisallow: /private\n','https://example.com/private')
