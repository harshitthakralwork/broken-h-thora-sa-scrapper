"""PostgreSQL backup command tests with mocks: no PostgreSQL server is contacted."""
import subprocess
from sqlalchemy.engine import make_url
import pytest
import manage

@pytest.fixture
def pg(monkeypatch,tmp_path):
    monkeypatch.setattr(manage,'url','postgresql+psycopg://sparkxflow:temporary-secret@127.0.0.1:55432/sparkxflow_verify')
    monkeypatch.setattr(manage,'parsed',make_url(manage.url))
    monkeypatch.setenv('SPARKXFLOW_BACKUP_DIR',str(tmp_path))
    for key in ('PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGUSER','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD','PGPASSFILE'):
        monkeypatch.delenv(key,raising=False)
    return tmp_path

def test_pg_backup_uses_same_explicit_target_and_hides_password(pg,monkeypatch):
    monkeypatch.setattr(manage.shutil,'which',lambda _: 'pg_dump')
    def fake_run(cmd,env,check,timeout):
        assert cmd[cmd.index('--host')+1]=='127.0.0.1'
        assert cmd[cmd.index('--port')+1]=='55432'
        assert cmd[cmd.index('--username')+1]=='sparkxflow'
        assert cmd[cmd.index('--dbname')+1]=='sparkxflow_verify'
        assert 'temporary-secret' not in ' '.join(cmd) and env['PGPASSWORD']=='temporary-secret'
        pg.joinpath(cmd[cmd.index('--file')+1]).write_bytes(b'fake-dump')
    monkeypatch.setattr(manage.subprocess,'run',fake_run)
    assert manage.backup().is_file()

def test_ambiguous_pg_environment_stops_before_backup(pg,monkeypatch):
    monkeypatch.setenv('PGHOSTADDR','192.0.2.1')
    monkeypatch.setattr(manage,'backup',lambda:pytest.fail('Backup must not run'))
    with pytest.raises(RuntimeError,match='Clear conflicting PG'): manage.migrate()

def test_failed_pg_dump_stops_before_schema_upgrade(pg,monkeypatch):
    monkeypatch.setattr(manage.shutil,'which',lambda _: 'pg_dump')
    monkeypatch.setattr(manage.subprocess,'run',lambda *a,**kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1,'pg_dump')))
    monkeypatch.setattr(manage,'upgrade_target',lambda:pytest.fail('Upgrade must not run'))
    with pytest.raises(subprocess.CalledProcessError): manage.migrate()

def test_pg_url_requires_explicit_port_and_user(pg,monkeypatch):
    monkeypatch.setattr(manage,'parsed',make_url('postgresql+psycopg://localhost/sparkxflow_verify'))
    with pytest.raises(RuntimeError,match='explicitly include'): manage.migrate()
