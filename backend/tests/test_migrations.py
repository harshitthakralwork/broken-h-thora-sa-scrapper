import os, sqlite3, subprocess, sys
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy.engine import URL
ROOT=Path(__file__).resolve().parents[2]

@contextmanager
def database(path):
    # sqlite3's context manager commits/rolls back but does NOT close connections.
    conn=sqlite3.connect(path,timeout=5)
    try:
        with conn: yield conn
    finally: conn.close()

def run(path):
    env=os.environ.copy(); env.update(ADMIN_TOKEN='test-admin-token-long-enough-for-migration', DATABASE_URL=str(URL.create('sqlite',database=path.as_posix())),PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', SPARKXFLOW_BACKUP_DIR=str(path.parent/'backups'), SPARKXFLOW_BACKUP_TIMEOUT_SECONDS='3')
    return subprocess.run([sys.executable,'backend/manage.py','migrate'],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=60)

def test_fresh_database_migrates(tmp_path):
    db=tmp_path/'new.db'; result=run(db)
    assert result.returncode==0, result.stderr
    with database(db) as c:
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0005_crawler_safety'
        assert c.execute('select count(*) from businesses').fetchone()[0]==0

def test_legacy_database_is_backed_up_and_preserved(tmp_path):
    db=tmp_path/'legacy.db'
    with database(db) as c:
        c.execute('''CREATE TABLE businesses (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(200) NOT NULL, website VARCHAR(2048) NOT NULL, domain VARCHAR(253), industry VARCHAR(120) NOT NULL, location VARCHAR(200) NOT NULL, source VARCHAR(2048) NOT NULL, created_at DATETIME NOT NULL, report TEXT NOT NULL, researched_at DATETIME, UNIQUE (domain))''')
        c.execute("insert into businesses values ('1','Keep me','','','','','manual','2025-01-01','old report',NULL)")
    result=run(db); assert result.returncode==0, result.stderr
    assert 'Verified SQLite backup' in result.stdout
    with database(db) as c:
        assert c.execute('select name,report from businesses').fetchone()==('Keep me','old report')
        assert c.execute('select report,kind from research_history').fetchone()==('old report','legacy')
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0005_crawler_safety'

def test_incompatible_database_is_not_stamped(tmp_path):
    db=tmp_path/'incompatible.db'
    with database(db) as c: c.execute('create table businesses (id text)')
    result=run(db); assert result.returncode!=0
    assert 'columns differ' in result.stderr, f'Unexpected failure; stdout={result.stdout!r}, stderr={result.stderr!r}'
    with database(db) as c:
        assert c.execute("select count(*) from sqlite_master where name='alembic_version'").fetchone()[0]==0

def test_incompatible_legacy_data_stops_before_stamping(tmp_path):
    db=tmp_path/'bad-data.db'
    with database(db) as c:
        c.execute('''CREATE TABLE businesses (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(200) NOT NULL, website VARCHAR(2048) NOT NULL, domain VARCHAR(253), industry VARCHAR(120) NOT NULL, location VARCHAR(200) NOT NULL, source VARCHAR(2048) NOT NULL, created_at DATETIME NOT NULL, report TEXT NOT NULL, researched_at DATETIME, UNIQUE (domain))''')
        c.execute("insert into businesses values ('1','Keep bad date','','','','','manual','not-a-date','report',NULL)")
    result=run(db)
    assert result.returncode!=0 and 'preflight failed' in result.stderr
    with database(db) as c:
        assert c.execute('select created_at,report from businesses').fetchone()==('not-a-date','report')
        assert c.execute("select count(*) from sqlite_master where name='alembic_version'").fetchone()[0]==0

def test_versioned_schema_mismatch_stops_without_modifying_original(tmp_path):
    db=tmp_path/'wrong-revision.db'
    with database(db) as c:
        c.execute('create table alembic_version (version_num varchar(32) not null)')
        c.execute("insert into alembic_version values ('0003_research_history')")
        c.execute('create table businesses (id text)')
    result=run(db)
    assert result.returncode!=0 and 'preflight failed' in result.stderr
    with database(db) as c:
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0003_research_history'
        assert c.execute("select count(*) from sqlite_master where name='research_history'").fetchone()[0]==0

def make_versioned(db,version):
    with database(db) as c:
        c.execute('''CREATE TABLE businesses (id VARCHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(200) NOT NULL, website VARCHAR(2048) NOT NULL, domain VARCHAR(253), industry VARCHAR(120) NOT NULL, location VARCHAR(200) NOT NULL, source VARCHAR(2048) NOT NULL, created_at DATETIME NOT NULL, report TEXT NOT NULL, researched_at DATETIME, UNIQUE (domain))''')
        c.execute("insert into businesses values ('lead-1','Existing','','','','','original','2025-01-01','original report',NULL)")
        c.execute('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)')
        c.execute('INSERT INTO alembic_version VALUES (?)',(version,))
        if version=='0002_duplicate_reviews':
            c.execute('''CREATE TABLE duplicate_reviews (id VARCHAR(36) NOT NULL PRIMARY KEY, incoming TEXT NOT NULL, matches TEXT NOT NULL, status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, resolved_at DATETIME)''')
            c.execute("insert into duplicate_reviews values ('review-1','incoming data','match data','pending','2025-01-01',NULL)")

def test_upgrade_existing_0001_preserves_lead_and_report(tmp_path):
    db=tmp_path/'baseline.db'; make_versioned(db,'0001_baseline')
    result=run(db); assert result.returncode==0, result.stderr
    with database(db) as c:
        assert c.execute('select name,report from businesses').fetchone()==('Existing','original report')
        assert c.execute('select report,kind from research_history').fetchone()==('original report','legacy')
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0005_crawler_safety'

def test_upgrade_existing_0002_preserves_review_and_report(tmp_path):
    db=tmp_path/'review.db'; make_versioned(db,'0002_duplicate_reviews')
    result=run(db); assert result.returncode==0, result.stderr
    with database(db) as c:
        assert c.execute('select incoming,matches,status from duplicate_reviews').fetchone()==('incoming data','match data','pending')
        assert c.execute('select report from research_history').fetchone()==('original report',)
        assert c.execute('select version_num from alembic_version').fetchone()[0]=='0005_crawler_safety'

def test_current_revision_migration_is_idempotent_and_backed_up(tmp_path):
    db=tmp_path/'current.db'; assert run(db).returncode==0
    with database(db) as c:
        c.execute("insert into businesses values ('lead-1','Preserved','','','','','original','2025-01-01','',NULL)")
        c.execute("insert into duplicate_reviews values ('review-1','data','matches','pending','2025-01-01',NULL)")
    again=run(db); assert again.returncode==0, again.stderr
    assert 'Verified SQLite backup' in again.stdout
    with database(db) as c:
        assert c.execute('select name from businesses').fetchone()==('Preserved',)
        assert c.execute('select incoming,status from duplicate_reviews').fetchone()==('data','pending')
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_non_ascii_and_reserved_path_characters(tmp_path, monkeypatch):
    directory=tmp_path/'café space # sample'; directory.mkdir()
    monkeypatch.setenv('TMPDIR',str(directory));monkeypatch.setenv('TEMP',str(directory));monkeypatch.setenv('TMP',str(directory))
    db=directory/'legacy.db'; make_versioned(db,'0001_baseline')
    result=run(db); assert result.returncode==0, (result.stdout,result.stderr)
    with database(db) as c: assert c.execute('select name from businesses').fetchone()==('Existing',)

def downgrade(db,revision):
    env=os.environ.copy();env.update(ADMIN_TOKEN='test-admin-token-long-enough-for-migration', DATABASE_URL=str(URL.create('sqlite',database=db.as_posix())),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','downgrade',revision],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=60)

def test_empty_additive_tables_can_be_downgraded_and_upgraded(tmp_path):
    db=tmp_path/'empty.db'; assert run(db).returncode==0
    down=downgrade(db,'0001_baseline'); assert down.returncode==0,down.stderr
    with database(db) as c:
        assert c.execute('select version_num from alembic_version').fetchone()==('0001_baseline',)
        assert c.execute("select count(*) from sqlite_master where name in ('duplicate_reviews','research_history')").fetchone()[0]==0
    up=run(db); assert up.returncode==0,up.stderr

def test_history_downgrade_refuses_to_delete_data(tmp_path):
    db=tmp_path/'with-history.db'; assert run(db).returncode==0
    with database(db) as c:
        c.execute("insert into businesses values ('1','Keep','','','','','manual','2025-01-01','',NULL)")
        c.execute("insert into research_history values ('h','1','legacy data','2025-01-01','legacy')")
    down=downgrade(db,'0002_duplicate_reviews')
    assert down.returncode!=0 and 'research history would be lost' in down.stderr
    with database(db) as c:
        assert c.execute('select report from research_history').fetchone()==('legacy data',)
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_review_downgrade_refuses_to_delete_data(tmp_path):
    db=tmp_path/'with-review.db'; assert run(db).returncode==0
    with database(db) as c: c.execute("insert into duplicate_reviews values ('r','incoming','matches','pending','2025-01-01',NULL)")
    down=downgrade(db,'0001_baseline')
    assert down.returncode!=0 and 'duplicate review records would be lost' in down.stderr
    with database(db) as c:
        assert c.execute('select incoming from duplicate_reviews').fetchone()==('incoming',)
        assert c.execute("select count(*) from sqlite_master where name='research_history'").fetchone()[0]==1
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_baseline_downgrade_is_blocked(tmp_path):
    db=tmp_path/'no-delete.db'; assert run(db).returncode==0
    down=downgrade(db,'base'); assert down.returncode!=0 and 'would delete business data' in down.stderr
    with database(db) as c:
        assert c.execute("select count(*) from sqlite_master where name in ('businesses','research_history','duplicate_reviews')").fetchone()[0]==3
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_versioned_column_type_mismatch_stops_before_changes(tmp_path):
    db=tmp_path/'wrong-column-type.db';make_versioned(db,'0002_duplicate_reviews')
    with database(db) as c:
        c.execute('ALTER TABLE duplicate_reviews RENAME TO old_duplicate_reviews')
        c.execute('''CREATE TABLE duplicate_reviews (id VARCHAR(36) NOT NULL PRIMARY KEY, incoming INTEGER NOT NULL, matches TEXT NOT NULL, status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL, resolved_at DATETIME)''')
        c.execute('INSERT INTO duplicate_reviews SELECT * FROM old_duplicate_reviews')
        c.execute('DROP TABLE old_duplicate_reviews')
    result=run(db); assert result.returncode!=0 and 'duplicate_reviews.incoming' in result.stderr
    with database(db) as c:
        assert c.execute('select incoming from duplicate_reviews').fetchone()==('incoming data',)
        assert c.execute('select version_num from alembic_version').fetchone()==('0002_duplicate_reviews',)
        assert c.execute("select count(*) from sqlite_master where name='research_history'").fetchone()[0]==0

def test_existing_0003_records_reports_and_review_are_preserved(tmp_path):
    db=tmp_path/'legacy-0003.db'; make_versioned(db,'0002_duplicate_reviews')
    with database(db) as c: c.execute("update businesses set website='https://legacy.example/',domain='legacy.example',source='Legacy directory' where id='lead-1'")
    env=os.environ.copy();env.update(ADMIN_TOKEN='test-admin-token-long-enough-for-migration',DATABASE_URL=str(URL.create('sqlite',database=db.as_posix())),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    old=subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','0003_research_history'],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=60)
    assert old.returncode==0,old.stderr
    with database(db) as c:
        before_business=c.execute('select * from businesses').fetchall()
        before_review=c.execute('select * from duplicate_reviews').fetchall()
        before_history=c.execute('select * from research_history').fetchall()
    result=run(db); assert result.returncode==0,result.stderr
    assert 'Verified SQLite backup' in result.stdout and 'preflight passed' in result.stdout
    with database(db) as c:
        assert c.execute('select * from businesses').fetchall()==before_business
        assert c.execute('select * from duplicate_reviews').fetchall()==before_review
        assert c.execute('select * from research_history').fetchall()==before_history
        assert c.execute('select business_id,domain from business_domains').fetchone()==('lead-1','legacy.example')
        assert c.execute('select business_id,source,kind from business_sources').fetchone()==('lead-1','Legacy directory','legacy')
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_new_identity_downgrade_refuses_to_delete_provenance(tmp_path):
    db=tmp_path/'with-provenance.db'; assert run(db).returncode==0
    with database(db) as c:
        c.execute("insert into businesses values ('1','Keep','','','','','manual','2025-01-01','',NULL)")
        c.execute("insert into business_sources values ('source-1','1','Original source','manual',NULL,NULL,'2025-01-01')")
    down=downgrade(db,'0003_research_history')
    assert down.returncode!=0 and 'history would be lost' in down.stderr
    with database(db) as c:
        assert c.execute('select source from business_sources').fetchone()==('Original source',)
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)

def test_migrated_legacy_database_supports_shared_domain_without_data_loss(tmp_path):
    db=tmp_path/'integration.db';make_versioned(db,'0002_duplicate_reviews')
    with database(db) as c:
        c.execute("update businesses set website='https://legacy.example/',domain='legacy.example',location='York',source='Legacy directory' where id='lead-1'")
    env=os.environ.copy();env.update(ADMIN_TOKEN='test-admin-token-long-enough-for-migration',DATABASE_URL=str(URL.create('sqlite',database=db.as_posix())),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONPATH='backend',SPARKXFLOW_BACKUP_DIR=str(tmp_path/'backups'))
    older=subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','0003_research_history'],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=60)
    assert older.returncode==0,older.stderr
    migrated=run(db); assert migrated.returncode==0,migrated.stderr
    script='''
from fastapi.testclient import TestClient
from app.main import app
headers={'Authorization':'Bearer test-admin-token-long-enough-for-migration'}
with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as c:
    assert c.get('/api/duplicate-reviews',headers=headers).status_code==200
    r=c.post('/api/leads',headers=headers,json={'name':'Existing','website':'https://legacy.example','location':'Leeds','source':'New directory'})
    assert r.status_code==200 and r.json()['status']=='review',r.text
    review=r.json()['review']
    assert review['classification']=='possible'
    r=c.post('/api/duplicate-reviews/'+review['id']+'/resolve',headers=headers,json={'decision':'separate_branch','matched_business_id':'lead-1'})
    assert r.status_code==200,r.text
    leads=c.get('/api/leads',headers=headers).json()
    assert len(leads)==2 and {x['domain'] for x in leads}=={'legacy.example'}
    assert c.get('/api/leads/lead-1/research-history',headers=headers).status_code==200
'''
    checked=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',errors='replace',timeout=60)
    assert checked.returncode==0,checked.stderr
    with database(db) as c:
        assert c.execute("select name,report,source from businesses where id='lead-1'").fetchone()==('Existing','original report','Legacy directory')
        assert c.execute("select incoming,matches,status from duplicate_reviews where id='review-1'").fetchone()==('incoming data','match data','pending')
        assert c.execute("select report from research_history where business_id='lead-1'").fetchone()==('original report',)
        assert c.execute('select count(*) from business_domains where domain=?',('legacy.example',)).fetchone()[0]==2

def test_backup_locked_database_fails_bounded_and_preserves_data(tmp_path):
    import time
    db=tmp_path/'locked.db'
    with database(db) as c:
        c.execute('create table businesses (id text)')
        c.execute("insert into businesses values ('keep')")
    locker=sqlite3.connect(db,timeout=1)
    try:
        locker.execute('BEGIN EXCLUSIVE')
        start=time.monotonic(); result=run(db); elapsed=time.monotonic()-start
        assert result.returncode!=0 and 'timed out' in result.stderr, (result.stdout,result.stderr)
        assert elapsed<10
    finally:
        locker.rollback(); locker.close()
    with database(db) as c:
        assert c.execute('select id from businesses').fetchone()==('keep',)
        assert c.execute("select count(*) from sqlite_master where name='alembic_version'").fetchone()[0]==0

def test_existing_0004_records_survive_crawler_safety_migration(tmp_path):
    db=tmp_path/'existing-0004.db'; assert run(db).returncode==0
    down=downgrade(db,'0004_identity_sources');assert down.returncode==0,down.stderr
    with database(db) as c:
        c.execute("insert into businesses values ('lead-1','Preserved','https://shared.example','shared.example','','York','Original','2025-01-01','legacy',NULL)")
        c.execute("insert into business_domains values ('lead-1','shared.example')")
        c.execute("insert into business_sources values ('src-1','lead-1','Original','legacy',NULL,NULL,'2025-01-01')")
        c.execute("insert into duplicate_reviews values ('rev-1','incoming','matches','pending','2025-01-01',NULL)")
        before=[c.execute(f'select * from {t}').fetchall() for t in ('businesses','business_domains','business_sources','duplicate_reviews')]
    result=run(db);assert result.returncode==0,result.stderr
    with database(db) as c:
        after=[c.execute(f'select * from {t}').fetchall() for t in ('businesses','business_domains','business_sources','duplicate_reviews')]
        assert after==before
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)
        assert c.execute("select count(*) from crawler_control where id='global'").fetchone()==(1,)

def test_crawler_safety_downgrade_refuses_to_erase_pacing_history(tmp_path):
    db=tmp_path/'with-pacing.db';assert run(db).returncode==0
    with database(db) as c: c.execute("insert into crawler_host_limits values ('example.com',100,NULL,0)")
    down=downgrade(db,'0004_identity_sources')
    assert down.returncode!=0 and 'coordination state would be lost' in down.stderr
    with database(db) as c:
        assert c.execute('select host from crawler_host_limits').fetchone()==('example.com',)
        assert c.execute('select version_num from alembic_version').fetchone()==('0005_crawler_safety',)
