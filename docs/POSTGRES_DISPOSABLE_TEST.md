# Disposable PostgreSQL verification on Windows 11

**Status:** This is a procedure for you to run; it was not executed in the Linux sandbox. It uses only throwaway dummy records in a new Docker container and two new test databases. It does not test your real database, and successful results do not prove production backup/restore readiness.

## Before starting

- Install and start Docker Desktop. Install PostgreSQL 17 client tools on Windows and ensure **both** `pg_dump --version` and `pg_restore --version` work in PowerShell. `pg_dump` must be the same major version as or newer than the PostgreSQL server.
- Run the normal Python environment setup from `README.md` first. Open a **new PowerShell window** in your project directory. Do not start the real SparkXFlow app in that window. Do not use your real PostgreSQL database, credentials or lead data. The script binds the throwaway container to `127.0.0.1:55432`; if the port is in use, stop and choose another free loopback port throughout the steps.
- The test container and its data are disposable. Passwords used below are temporary, and Docker may expose its container environment to local administrators. Backups are unencrypted dummy data under a unique temporary directory. Use the environment variables only in this PowerShell window.

### 1. Create an isolated container

```powershell
cd C:\Projects\sparkxflow-lead-engine
$ErrorActionPreference = 'Stop'
pg_dump --version
if ($LASTEXITCODE -ne 0) { throw 'pg_dump unavailable' }
pg_restore --version
if ($LASTEXITCODE -ne 0) { throw 'pg_restore unavailable' }

# Clear libpq connection overrides in this PowerShell session only.
foreach ($n in @('PGHOST','PGHOSTADDR','PGPORT','PGDATABASE','PGUSER','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD','PGPASSFILE')) {
  Remove-Item "Env:$n" -ErrorAction SilentlyContinue
}
$Password = .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$Container = 'sxverify-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$env:ADMIN_TOKEN = .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(40))"
$env:SPARKXFLOW_BACKUP_DIR = Join-Path $env:TEMP ("sxverify-backups-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $env:SPARKXFLOW_BACKUP_DIR | Out-Null

docker run -d --name $Container -p 127.0.0.1:55432:5432 `
  -e POSTGRES_USER=sparkxflow -e "POSTGRES_PASSWORD=$Password" `
  -e POSTGRES_DB=postgres postgres:17
if ($LASTEXITCODE -ne 0) { throw 'Container did not start; do not continue.' }
$Ready = $false
for ($i=0; $i -lt 30; $i++) {
  docker exec $Container pg_isready -U sparkxflow -d postgres *> $null
  if ($LASTEXITCODE -eq 0) { $Ready = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $Ready) { throw 'Database did not become ready; do not continue.' }
docker exec $Container createdb -U sparkxflow sx_fresh
if ($LASTEXITCODE -ne 0) { throw 'Could not create fresh test database.' }
docker exec $Container createdb -U sparkxflow sx_legacy
if ($LASTEXITCODE -ne 0) { throw 'Could not create legacy test database.' }
docker exec $Container createdb -U sparkxflow sx_restore
if ($LASTEXITCODE -ne 0) { throw 'Could not create empty restore database.' }
```

### 2. Test a fresh migration

```powershell
$env:DATABASE_URL = "postgresql+psycopg://sparkxflow:${Password}@127.0.0.1:55432/sx_fresh"
.venv\Scripts\python.exe backend\manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Fresh migration failed; stop and retain the output.' }
docker exec $Container psql -X -v ON_ERROR_STOP=1 -U sparkxflow -d sx_fresh -c "SELECT version_num FROM alembic_version;"
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect fresh database.' }
```

Confirm the output is `0005_crawler_safety`. The command should also report a dump in the unique test backup directory.

### 3. Test migration of an unversioned legacy database with dummy data

```powershell
@'
CREATE TABLE businesses (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  website VARCHAR(2048) NOT NULL,
  domain VARCHAR(253) UNIQUE,
  industry VARCHAR(120) NOT NULL,
  location VARCHAR(200) NOT NULL,
  source VARCHAR(2048) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  report TEXT NOT NULL,
  researched_at TIMESTAMP WITH TIME ZONE
);
INSERT INTO businesses VALUES
  ('dummy-1','Dummy business','https://dummy.example','dummy.example','','','test','2025-01-01T00:00:00Z','dummy legacy report',NULL);
'@ | docker exec -i $Container psql -X -v ON_ERROR_STOP=1 -U sparkxflow -d sx_legacy
if ($LASTEXITCODE -ne 0) { throw 'Could not create dummy legacy schema.' }

$env:DATABASE_URL = "postgresql+psycopg://sparkxflow:${Password}@127.0.0.1:55432/sx_legacy"
.venv\Scripts\python.exe backend\manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Legacy migration failed; stop and retain the output and backup.' }
@'
DO $$ BEGIN
  IF (SELECT count(*) FROM businesses WHERE id='dummy-1' AND report='dummy legacy report') <> 1 THEN
    RAISE EXCEPTION 'Legacy business was not preserved';
  END IF;
  IF (SELECT count(*) FROM research_history WHERE business_id='dummy-1' AND report='dummy legacy report' AND kind='legacy') <> 1 THEN
    RAISE EXCEPTION 'Legacy report was not preserved in history';
  END IF;
  IF (SELECT count(*) FROM business_domains WHERE business_id='dummy-1' AND domain='dummy.example') <> 1 THEN
    RAISE EXCEPTION 'Legacy domain association missing';
  END IF;
  IF (SELECT count(*) FROM business_sources WHERE business_id='dummy-1' AND source='test') <> 1 THEN
    RAISE EXCEPTION 'Legacy source missing';
  END IF;
  IF (SELECT count(*) FROM crawler_control WHERE id='global') <> 1 THEN
    RAISE EXCEPTION 'Crawler coordination control missing';
  END IF;
  IF (SELECT version_num FROM alembic_version) <> '0005_crawler_safety' THEN
    RAISE EXCEPTION 'Unexpected revision';
  END IF;
END $$;
'@ | docker exec -i $Container psql -X -v ON_ERROR_STOP=1 -U sparkxflow -d sx_legacy
if ($LASTEXITCODE -ne 0) { throw 'Legacy preservation check failed.' }

# A second run makes a backup of the migrated dummy database and checks the current revision.
.venv\Scripts\python.exe backend\manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Repeat migration failed.' }
```

### 4. Restore the migrated dummy backup into the separate empty test database

```powershell
$Dump = Get-ChildItem -Path $env:SPARKXFLOW_BACKUP_DIR -Filter 'postgres-*.dump' |
  Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $Dump) { throw 'No test backup found.' }
$env:PGPASSWORD = $Password
try {
  pg_restore --exit-on-error --no-owner --no-privileges -h 127.0.0.1 -p 55432 `
    -U sparkxflow -d sx_restore $Dump.FullName
  if ($LASTEXITCODE -ne 0) { throw 'Restore failed.' }
} finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
@'
DO $$ BEGIN
  IF (SELECT count(*) FROM businesses WHERE id='dummy-1' AND report='dummy legacy report') <> 1 THEN
    RAISE EXCEPTION 'Restored business missing';
  END IF;
  IF (SELECT count(*) FROM research_history WHERE business_id='dummy-1' AND report='dummy legacy report') <> 1 THEN
    RAISE EXCEPTION 'Restored history missing';
  END IF;
END $$;
'@ | docker exec -i $Container psql -X -v ON_ERROR_STOP=1 -U sparkxflow -d sx_restore
if ($LASTEXITCODE -ne 0) { throw 'Restored data verification failed.' }
Write-Host 'Disposable PostgreSQL checks passed. Test backups:' $env:SPARKXFLOW_BACKUP_DIR
```

On success, only **this disposable test** passed. On any failure, stop and retain the terminal output and dummy backup for diagnosis. Do not continue against real data.

### 5. Optional cleanup

Verify `$Container` refers to the newly created `sxverify-...` container before removing it; this deletes that container's **dummy test data**. Retain the dummy backups as long as needed. Close this PowerShell window afterwards to discard its temporary environment variables.

```powershell
Write-Host "Disposable container: $Container"
docker rm -f $Container
```
