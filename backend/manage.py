"""Explicitly back up and migrate local database. Never stamps an unverified legacy schema."""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url, URL
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
url = os.environ.get('DATABASE_URL', 'sqlite:///./sparkxflow.db')
parsed = make_url(url)
config = Config(str(ROOT / 'backend' / 'alembic.ini'))
LEGACY = {'id':('VARCHAR(36)',False), 'name':('VARCHAR(200)',False), 'website':('VARCHAR(2048)',False), 'domain':('VARCHAR(253)',True), 'industry':('VARCHAR(120)',False), 'location':('VARCHAR(200)',False), 'source':('VARCHAR(2048)',False), 'created_at':('DATETIME',False), 'report':('TEXT',False), 'researched_at':('DATETIME',True)}

def backup():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    outdir=Path(os.environ.get('SPARKXFLOW_BACKUP_DIR', str(ROOT/'backups'))).resolve(); outdir.mkdir(parents=True,exist_ok=True)
    if parsed.get_backend_name() == 'sqlite':
        if not parsed.database or parsed.database == ':memory:': raise RuntimeError('In-memory SQLite databases cannot be safely backed up by this tool.')
        path=Path(parsed.database).resolve()
        if not path.exists(): print('New SQLite database: no existing file to back up.'); return None
        out=outdir/f'{path.stem}-{stamp}.db'
        partial=out.with_suffix('.db.partial')
        backup_timeout=float(os.environ.get('SPARKXFLOW_BACKUP_TIMEOUT_SECONDS','120'))
        if not 1<=backup_timeout<=3600: raise ValueError('Invalid SQLite backup timeout; expected 1–3600 seconds')
        cutoff=time.monotonic()+backup_timeout
        def progress(status,remaining,total):
            if time.monotonic()>cutoff:
                raise TimeoutError('SQLite backup timed out; stop all database writers and retry. Migration stopped.')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)) as src, closing(sqlite3.connect(partial,timeout=1)) as dst:
            src.backup(dst,pages=256,progress=progress,sleep=0.05)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('Backup integrity check failed; migration stopped.')
        os.replace(partial,out)
        print('Verified SQLite backup:',out)
        return out
    elif parsed.get_backend_name() == 'postgresql':
        if not shutil.which('pg_dump'): raise RuntimeError('pg_dump not found. Install matching PostgreSQL client tools and retry; migration stopped.')
        out=outdir/f'postgres-{stamp}.dump'
        env=os.environ.copy()
        if parsed.password: env['PGPASSWORD']=parsed.password
        cmd=['pg_dump','--format=custom','--file',str(out),'--no-password']
        if parsed.host: cmd+=['--host',parsed.host]
        if parsed.port: cmd+=['--port',str(parsed.port)]
        if parsed.username: cmd+=['--username',parsed.username]
        cmd+=['--dbname',parsed.database or '']
        subprocess.run(cmd,env=env,check=True,timeout=300)
        if not out.is_file() or not out.stat().st_size: raise RuntimeError('PostgreSQL backup failed; migration stopped.')
        print('PostgreSQL backup created:',out,'(restore-test separately)')
        return out
    else: raise RuntimeError('Unsupported database; migration stopped.')

def verify_business(inspector):
    cols={c['name']:c for c in inspector.get_columns('businesses')}
    if set(cols)!=set(LEGACY): raise RuntimeError('Legacy businesses columns differ from the expected baseline. Migration stopped.')
    for name,(expected,nullable) in LEGACY.items():
        col=cols[name]; typ=str(col['type']).upper()
        # SQLite stores timezone-aware datetimes as DATETIME; PostgreSQL reflects TIMESTAMP.
        if expected=='DATETIME': valid=typ.startswith(('DATETIME','TIMESTAMP'))
        else: valid=typ==expected
        if not valid or bool(col['nullable'])!=nullable: raise RuntimeError(f'Legacy column {name} differs from the expected baseline. Migration stopped.')
    if inspector.get_pk_constraint('businesses').get('constrained_columns') != ['id']: raise RuntimeError('Unexpected primary key; migration stopped.')
    uniques=inspector.get_unique_constraints('businesses')
    if not any(c.get('column_names') == ['domain'] for c in uniques): raise RuntimeError('Expected domain uniqueness is missing; migration stopped.')

def verify_legacy(engine):
    inspector=inspect(engine); tables=set(inspector.get_table_names())
    if tables != {'businesses'}: raise RuntimeError(f'Unversioned database has unexpected tables {sorted(tables)}. Do not stamp; seek a migration review.')
    verify_business(inspector)

def verify_versioned(engine):
    inspector=inspect(engine)
    with engine.connect() as connection:
        rows=connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalars().all()
    revisions=['0001_baseline','0002_duplicate_reviews','0003_research_history','0004_identity_sources','0005_crawler_safety']
    if len(rows)!=1 or rows[0] not in revisions: raise RuntimeError('Unknown database revision; migration stopped for review.')
    version=rows[0]; tables={'businesses','alembic_version'}
    if version in revisions[1:]: tables.add('duplicate_reviews')
    if version in revisions[2:]: tables.add('research_history')
    if version in revisions[3:]: tables.update({'identity_guard','business_domains','import_batches','import_candidates','business_sources','business_relationships','review_resolutions'})
    if version in revisions[4:]: tables.update({'crawler_control','crawler_leases','crawler_host_limits'})
    app_tables = {'contacts', 'campaigns', 'outreach_messages', 'inbox_messages', 'follow_up_tasks', 'suppression_list', 'sales_pipeline', 'system_integrations', 'automation_jobs', 'business_profiles', 'search_jobs', 'discovery_hypotheses', 'source_connectors', 'lead_qualifications'}
    if set(inspector.get_table_names()) - app_tables != tables: raise RuntimeError('Versioned database tables do not match its revision; migration stopped.')
    verify_business(inspector)
    expected={
      'duplicate_reviews':{'id':('VARCHAR(36)',False),'incoming':('TEXT',False),'matches':('TEXT',False),'status':('VARCHAR(20)',False),'created_at':('DATETIME',False),'resolved_at':('DATETIME',True)},
      'research_history':{'id':('VARCHAR(36)',False),'business_id':('VARCHAR(36)',False),'report':('TEXT',False),'collected_at':('DATETIME',False),'kind':('VARCHAR(20)',False)}}
    for table in tables & set(expected):
        columns={c['name']:c for c in inspector.get_columns(table)}
        if set(columns)!=set(expected[table]):
            raise RuntimeError(f'{table} columns do not match the recorded revision; migration stopped.')
        for name,(type_name,nullable) in expected[table].items():
            actual=str(columns[name]['type']).upper()
            valid=actual.startswith(('DATETIME','TIMESTAMP')) if type_name=='DATETIME' else actual==type_name
            if not valid or bool(columns[name]['nullable'])!=nullable:
                raise RuntimeError(f'{table}.{name} does not match the recorded revision; migration stopped.')
        if inspector.get_pk_constraint(table).get('constrained_columns')!=['id']:
            raise RuntimeError(f'{table} primary key does not match the recorded revision; migration stopped.')
    if version in revisions[3:]:
        additional={
          'identity_guard':({'id','counter'},['id']),
          'business_domains':({'business_id','domain'},['business_id']),
          'import_batches':({'id','original_csv','created_at'},['id']),
          'import_candidates':({'id','batch_id','row_number','raw_data','status','business_id','review_id','error','created_at'},['id']),
          'business_sources':({'id','business_id','source','kind','candidate_id','review_id','created_at'},['id']),
          'business_relationships':({'id','subject_business_id','related_business_id','relation','review_id','created_at'},['id']),
          'review_resolutions':({'id','review_id','decision','matched_business_id','result_business_id','created_at'},['id'])}
        for table,(names,primary) in additional.items():
            if {c['name'] for c in inspector.get_columns(table)}!=names or inspector.get_pk_constraint(table).get('constrained_columns')!=primary:
                raise RuntimeError(f'{table} does not match the recorded revision; migration stopped.')
        with engine.connect() as connection:
            if connection.exec_driver_sql("SELECT COUNT(*) FROM identity_guard WHERE id='global'").scalar()!=1:
                raise RuntimeError('Identity guard is missing; migration stopped.')
    if version==revisions[4]:
        for table,names,primary in [('crawler_control',{'id','counter'},['id']),('crawler_leases',{'id','expires_at'},['id']),('crawler_host_limits',{'host','next_allowed','owner','active_until'},['host'])]:
            if {c['name'] for c in inspector.get_columns(table)}!=names or inspector.get_pk_constraint(table).get('constrained_columns')!=primary:
                raise RuntimeError(f'{table} does not match the recorded revision; migration stopped.')
        with engine.connect() as connection:
            if connection.exec_driver_sql("SELECT COUNT(*) FROM crawler_control WHERE id='global'").scalar()!=1:
                raise RuntimeError('Crawler control is missing; migration stopped.')
    if 'research_history' in tables:
        fks=inspector.get_foreign_keys('research_history')
        if not any(fk.get('constrained_columns')==['business_id'] and fk.get('referred_table')=='businesses' and fk.get('referred_columns')==['id'] for fk in fks):
            raise RuntimeError('Research history foreign key does not match the recorded revision; migration stopped.')

def upgrade_target():
    engine=create_engine(url)
    try:
        tables=set(inspect(engine).get_table_names())
        if tables and 'alembic_version' not in tables:
            verify_legacy(engine)
            print('Verified Foundation v0.1 baseline; stamping existing schema.')
            command.stamp(config,'0001_baseline')
        elif 'alembic_version' in tables:
            verify_versioned(engine)
        command.upgrade(config,'head')
        print('Database migration completed.')
    finally: engine.dispose()

def migrate():
    if parsed.query:
        raise RuntimeError('Database URL query parameters are not supported by the backup tool. Migration stopped to avoid backing up the wrong target.')
    if parsed.get_backend_name()=='postgresql':
        if parsed.host not in ('localhost','127.0.0.1','::1'):
            raise RuntimeError('Only local PostgreSQL hosts are supported. Migration stopped.')
        if not parsed.username or not parsed.database or not parsed.port:
            raise RuntimeError('PostgreSQL URL must explicitly include username, port and database. Migration stopped.')
        # libpq environment defaults could silently redirect pg_dump or SQLAlchemy to different targets.
        conflicting=('PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGUSER','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD','PGPASSFILE')
        if any(os.environ.get(key) for key in conflicting):
            raise RuntimeError('Clear conflicting PG connection environment variables before migrating. Migration stopped.')
    backup_path=backup()
    if parsed.get_backend_name()=='sqlite' and backup_path:
        # Rehearse on a disposable copy before touching the original SQLite database.
        with tempfile.TemporaryDirectory(prefix='sparkxflow-preflight-') as temp:
            copy=Path(temp)/'preflight.db'
            shutil.copy2(backup_path,copy)
            env=os.environ.copy(); env['DATABASE_URL']=str(URL.create('sqlite',database=copy.as_posix())); env['PYTHONIOENCODING']='utf-8'
            preflight_code = "import sys, manage\ntry:\n manage.upgrade_target()\nexcept Exception as exc:\n print('Preflight failed:', str(exc), file=sys.stderr)\n sys.exit(1)"
            result=subprocess.run([sys.executable,'-c',preflight_code],cwd=ROOT/'backend',env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
            if result.returncode:
                raise RuntimeError('SQLite migration preflight failed; original database not changed. '+result.stderr.strip()[:500])
            print('SQLite migration preflight passed on a backup copy.')
    upgrade_target()

if __name__=='__main__':
    if sys.argv[1:] != ['migrate']:
        print('Usage: python backend/manage.py migrate',file=sys.stderr); sys.exit(2)
    try: migrate()
    except Exception as exc:
        print('Migration stopped:',str(exc),file=sys.stderr); sys.exit(1)
