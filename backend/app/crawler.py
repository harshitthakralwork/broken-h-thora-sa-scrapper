"""User-initiated public page fetching with durable cross-process coordination.

No discovery, evasion, email, or AI. Called inside a killable worker process.
"""
import http.client
import ipaddress
import math
import re
import socket
import ssl
import time
import urllib.parse
import uuid
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

MAX_CONCURRENT=2
MIN_HOST_INTERVAL=1.0
SOCKET_TIMEOUT=5.0
MAX_BYTES=1_000_000

class CrawlBusy(Exception): pass
class CrawlDeadline(Exception): pass
class CrawlBlocked(Exception): pass

class Coordinator:
    def __init__(self,database_url,host_interval=MIN_HOST_INTERVAL):
        parsed=make_url(database_url)
        if parsed.get_backend_name() not in ('sqlite','postgresql'): raise CrawlBlocked('Unsupported coordination store')
        if parsed.get_backend_name()=='sqlite' and (not parsed.database or parsed.database==':memory:'): raise CrawlBlocked('A file-backed SQLite database is required')
        if parsed.get_backend_name()=='postgresql' and parsed.host not in ('localhost','127.0.0.1','::1'): raise CrawlBlocked('Only a local database is allowed')
        args={'timeout':1} if parsed.get_backend_name()=='sqlite' else {'connect_timeout':2}
        self.engine=create_engine(database_url,connect_args=args,pool_pre_ping=True)
        self.interval=max(float(host_interval),0.0)

    @contextmanager
    def locked(self):
        with self.engine.begin() as conn:
            if conn.dialect.name=='postgresql':
                conn.execute(text("SET LOCAL lock_timeout = '1s'"))
                conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            result=conn.execute(text("UPDATE crawler_control SET counter=counter WHERE id='global'"))
            if result.rowcount!=1: raise CrawlBlocked('Crawler coordination is not initialized')
            yield conn

    @contextmanager
    def lease(self,total_seconds):
        lease_id=str(uuid.uuid4()); now=time.time()
        with self.locked() as conn:
            conn.execute(text('DELETE FROM crawler_leases WHERE expires_at <= :now'),{'now':now})
            count=conn.execute(text('SELECT COUNT(*) FROM crawler_leases')).scalar_one()
            if count>=MAX_CONCURRENT: raise CrawlBusy('Research capacity is busy')
            conn.execute(text('INSERT INTO crawler_leases (id,expires_at) VALUES (:id,:expires)'),{'id':lease_id,'expires':now+total_seconds+5})
        try: yield lease_id
        finally:
            try:
                with self.locked() as conn: conn.execute(text('DELETE FROM crawler_leases WHERE id=:id'),{'id':lease_id})
            except Exception:
                pass  # A killed or interrupted worker leaves a lease that expires safely.

    @contextmanager
    def host_permit(self,host,deadline):
        owner=str(uuid.uuid4())
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0: raise CrawlDeadline('Total deadline exceeded')
            wait=0.0; acquired=False
            with self.locked() as conn:
                t=time.time()
                row=conn.execute(text('SELECT next_allowed,owner,active_until FROM crawler_host_limits WHERE host=:host'),{'host':host}).first()
                if row is None:
                    conn.execute(text('INSERT INTO crawler_host_limits (host,next_allowed,owner,active_until) VALUES (:host,:next,:owner,:until)'),{'host':host,'next':t,'owner':owner,'until':t+remaining+5})
                    acquired=True
                else:
                    cooldown=max(float(row.next_allowed)-t,0.0)
                    active=max(float(row.active_until)-t,0.0) if row.owner else 0.0
                    # Active requests often finish before their safety lease expires.
                    # Poll their release rather than treating the full lease as a delay.
                    wait=max(cooldown,min(active,0.1))
                    if wait<=0:
                        conn.execute(text('UPDATE crawler_host_limits SET owner=:owner,active_until=:until WHERE host=:host'),{'owner':owner,'until':t+remaining+5,'host':host})
                        acquired=True
            if acquired: break
            remaining=deadline-time.monotonic()
            if wait>=remaining: raise CrawlDeadline('Pacing would exceed total deadline')
            time.sleep(min(wait,remaining))
        try: yield
        finally:
            try:
                with self.locked() as conn:
                    row=conn.execute(text('SELECT next_allowed FROM crawler_host_limits WHERE host=:host AND owner=:owner'),{'host':host,'owner':owner}).first()
                    if row:
                        next_time=max(float(row.next_allowed),time.time()+self.interval)
                        conn.execute(text('UPDATE crawler_host_limits SET next_allowed=:next,owner=NULL,active_until=0 WHERE host=:host AND owner=:owner'),{'next':next_time,'host':host,'owner':owner})
            except Exception:
                pass  # A stale host permit expires after its worker's deadline.

    def pace(self,host,deadline):
        # Test/helper operation: acquire and immediately release the host permit.
        with self.host_permit(host,deadline): pass

    def defer(self,host,seconds):
        if seconds<=0: return
        with self.locked() as conn:
            t=time.time()+seconds
            existing=conn.execute(text('SELECT next_allowed FROM crawler_host_limits WHERE host=:host'),{'host':host}).scalar_one_or_none()
            if existing is None:
                conn.execute(text('INSERT INTO crawler_host_limits (host,next_allowed,owner,active_until) VALUES (:host,:t,NULL,0)'),{'host':host,'t':t})
            elif t>existing:
                conn.execute(text('UPDATE crawler_host_limits SET next_allowed=:t WHERE host=:host'),{'host':host,'t':t})

    def close(self): self.engine.dispose()

def target_parts(url):
    if any(ord(c)<32 or ord(c)==127 for c in url): raise CrawlBlocked('Invalid URL')
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username is not None or p.password is not None: raise CrawlBlocked('Invalid URL')
    port=p.port or (443 if p.scheme=='https' else 80)
    if (p.scheme,port) not in (('http',80),('https',443)): raise CrawlBlocked('Nonstandard port')
    host=p.hostname.lower().rstrip('.').encode('idna').decode('ascii')
    if not host or len(host)>253: raise CrawlBlocked('Invalid host')
    decoded=urllib.parse.unquote(p.path or '/')
    if '\\' in decoded or any(part in ('.','..') for part in decoded.split('/')) or re.search(r'%[0-9a-fA-F]{2}',decoded) or any(ord(c)<32 for c in decoded):
        raise CrawlBlocked('Ambiguous URL path')
    return p,host,port

def is_public_ip(value):
    ip=ipaddress.ip_address(value)
    if not ip.is_global: return False
    # Avoid ambiguous translation/tunnel and version-dependent special ranges.
    if isinstance(ip,ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None: return False
        if any(ip in ipaddress.ip_network(n) for n in ('64:ff9b::/96','64:ff9b:1::/48','2001::/32','2002::/16')): return False
    elif ip in ipaddress.ip_network('192.0.0.0/24'):
        return False
    return True

def checked_request(url,coordinator,deadline):
    p,host,port=target_parts(url)
    addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    ips=list(dict.fromkeys(x[4][0] for x in addresses))
    if not ips or any(not is_public_ip(ip) for ip in ips): raise CrawlBlocked('Only public IP addresses are allowed')
    ip=ips[0]
    remaining=deadline-time.monotonic()
    if remaining<=0: raise CrawlDeadline('Total deadline exceeded')
    timeout=min(SOCKET_TIMEOUT,remaining)
    if p.scheme=='https':
        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self):
                sock=socket.create_connection((ip,port),timeout=timeout)
                try: self.sock=ssl.create_default_context().wrap_socket(sock,server_hostname=host)
                except Exception: sock.close(); raise
        conn=PinnedHTTPS(host,port,timeout=timeout)
    else: conn=http.client.HTTPConnection(ip,port,timeout=timeout)
    path=urllib.parse.urlunsplit(('', '',p.path or '/',p.query,''))
    host_header='['+host+']' if ':' in host else host
    try:
        conn.request('GET',path,headers={'Host':host_header,'User-Agent':'SparkXFlowResearchBot/0.1','Accept':'text/html,text/plain;q=0.9,*/*;q=0.1','Connection':'close'})
        response=conn.getresponse(); body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES: raise CrawlBlocked('Response too large')
        if time.monotonic()>=deadline: raise CrawlDeadline('Total deadline exceeded')
        return response.status,dict(response.getheaders()),body
    finally: conn.close()

def header(headers,name): return next((v for k,v in headers.items() if k.lower()==name.lower()),'')

def robots_rules(body,url):
    """Conservative: apply every matching group's Disallow, ignoring Allow exceptions.

    May reject pages a full RFC 9309 implementation would allow; never treat an
    Allow directive as permission to bypass a conflicting Disallow.
    """
    groups=[]; agents=[]; directives=[]; seen=False
    for raw in body.decode('utf-8','replace').splitlines():
        line=raw.split('#',1)[0].strip()
        if ':' not in line: continue
        key,value=(x.strip() for x in line.split(':',1)); key=key.lower()
        if key=='user-agent':
            if seen:
                groups.append((agents,directives)); agents=[]; directives=[]; seen=False
            agents.append(value.lower())
        elif agents:
            directives.append((key,value)); seen=True
    if agents: groups.append((agents,directives))
    p,_,_=target_parts(url)
    target=urllib.parse.unquote((p.path or '/')+('?' + p.query if p.query else ''))
    delay=0.0
    for agents,rules in groups:
        if not any(a=='*' or (a and a in 'sparkxflowresearchbot/0.1') for a in agents): continue
        for key,value in rules:
            if key=='disallow' and value:
                anchored=value.endswith('$')
                if anchored: value=value[:-1]
                value=urllib.parse.unquote(value)
                pattern='^'+re.escape(value).replace(r'\*','.*')+('$' if anchored else '')
                if re.search(pattern,target): raise CrawlBlocked('robots.txt disallows this page')
            elif key=='crawl-delay':
                try:
                    amount=float(value)
                    if math.isfinite(amount) and amount>=0: delay=max(delay,amount)
                except ValueError: pass
            elif key=='request-rate':
                try:
                    requests,seconds=value.split('/',1); requests=int(requests); seconds=float(seconds)
                    if requests>0 and seconds>=0 and math.isfinite(seconds): delay=max(delay,seconds/requests)
                except (ValueError,ZeroDivisionError): pass
    return delay

def fetch_public_page(url,coordinator,deadline):
    for _ in range(4):
        p,host,_=target_parts(url)
        robots=urllib.parse.urlunsplit((p.scheme,p.netloc,'/robots.txt','',''))
        with coordinator.host_permit(host,deadline):
            status,headers,body=checked_request(robots,coordinator,deadline)
            if status==200:
                content_type=header(headers,'content-type').lower()
                if content_type and not content_type.startswith('text/plain'): raise CrawlBlocked('Unexpected robots.txt content type')
                delay=robots_rules(body,url)
                coordinator.defer(host,delay)
            elif status not in (404,410): raise CrawlBlocked('Could not confirm robots.txt permission')
        with coordinator.host_permit(host,deadline):
            status,headers,body=checked_request(url,coordinator,deadline)
        if status in (301,302,303,307,308):
            location=header(headers,'location')
            if not location: raise CrawlBlocked('Redirect without location')
            next_url=urllib.parse.urljoin(url,location)
            next_parts,_,_=target_parts(next_url)
            if p.scheme=='https' and next_parts.scheme!='https': raise CrawlBlocked('HTTPS downgrade redirect rejected')
            url=next_url; continue
        if status!=200: raise CrawlBlocked('Website request failed')
        content_type=header(headers,'content-type')
        if 'text/html' not in content_type.lower(): raise CrawlBlocked('Response was not HTML')
        charset_match=re.search(r'charset\s*=\s*[\"\']?([A-Za-z0-9._-]+)',content_type,re.I)
        try: decoded=body.decode(charset_match.group(1) if charset_match else 'utf-8','replace')
        except LookupError: decoded=body.decode('utf-8','replace')
        return url,decoded
    raise CrawlBlocked('Too many redirects')
