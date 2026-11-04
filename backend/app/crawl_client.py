"""Enforce a wall-clock bound around a single self-terminating crawler process."""
import json
import os
import subprocess
import sys
from pathlib import Path

TOTAL_DEADLINE_SECONDS=20.0
WORKER=Path(__file__).with_name('crawl_worker.py')
class CrawlTimeout(Exception): pass
class CrawlCapacity(Exception): pass
class CrawlFailure(Exception): pass

def run_crawl(url,database_url,deadline_seconds=TOTAL_DEADLINE_SECONDS,worker_path=WORKER):
    if not 0<deadline_seconds<=60: raise ValueError('Invalid crawl deadline')
    env=os.environ.copy(); env['DATABASE_URL']=database_url; env.pop('ADMIN_TOKEN',None);env['PYTHONIOENCODING']='utf-8'
    proc=subprocess.Popen([sys.executable,str(worker_path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,text=True,encoding='utf-8',errors='replace')
    try:
        stdout,_=proc.communicate(json.dumps({'url':url,'deadline_seconds':deadline_seconds}),timeout=deadline_seconds)
    except subprocess.TimeoutExpired:
        proc.kill();proc.communicate();raise CrawlTimeout('Research exceeded the total deadline')
    if proc.returncode==124: raise CrawlTimeout('Research exceeded the total deadline')
    if proc.returncode!=0: raise CrawlFailure('Research worker failed')
    try: result=json.loads(stdout)
    except (ValueError,TypeError): raise CrawlFailure('Research worker returned invalid output')
    if not isinstance(result,dict): raise CrawlFailure('Research worker returned invalid output')
    if result.get('code')=='busy': raise CrawlCapacity('Research capacity is busy')
    if result.get('code')=='deadline': raise CrawlTimeout('Research exceeded the total deadline')
    if not result.get('ok') or not isinstance(result.get('url'),str) or not isinstance(result.get('html'),str): raise CrawlFailure('Research did not complete')
    return result['url'],result['html']
