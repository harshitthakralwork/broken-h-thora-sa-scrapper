# Migration reliability and manual crawler safety — verification report

## Outcome and scope

The previous shared-domain identity and provenance work is retained. Research remains manually requested for a specified website; no autonomous discovery, background scraping, AI scoring, paid services, or email sending was added. Robots permission is not legal permission. Local-only operation, review of uncertain identities, and preservation of lead/report/import data remain requirements.

## Migration hang investigation

The complete original migration module did **not** reproduce the reported hang in this Linux environment (17 passed in 23.98 seconds before the additional migration test). Therefore the other environment's root cause is **not confirmed**, and its reliability cannot be claimed without running there.

Plausible cumulative isolation/lock issues were mitigated: SQLite test connections and backup connections are explicitly closed; migration-test subprocesses have a 60-second timeout; SQLite backup copy checks a monotonic deadline in its progress callback (120 seconds by default, configurable from 1 to 3600 with `SPARKXFLOW_BACKUP_TIMEOUT_SECONDS`); and migration rehearsal and `pg_dump` subprocesses each have a 300-second timeout. Integrity checking after a SQLite copy is not covered by the copy deadline. Slow systems may fail on a timeout rather than hanging. A `.db.partial` is unverified and must not be treated as a usable backup. Stop database writers before retrying. A real exclusive-lock test confirms backup timeout stops migration without changing the tested row or revision.

The expanded module was run twice sequentially after all test changes: **20 passed in 30.62s** and **20 passed in 30.36s**. These results are for this environment only. Tests include preserving populated 0004 records through 0005 and refusing downgrade when crawler pacing state exists.

## Safety implementation

- `backend/app/crawl_client.py` runs a fixed one-shot subprocess and kills and reaps it on timeout; `crawl_worker.py` has an independent watchdog. The normal 20-second budget includes DNS, network operations, robots, pacing, redirects, and worker processing. The worker's watchdog also covers blocked output. OS process creation/scheduling, uninterruptible kernel stalls or termination can exceed the nominal budget.
- `backend/app/crawler.py` restricts requests to public IPs and standard HTTP(S) ports, pins a validated address, validates HTTPS certificates, validates each redirect and refuses HTTPS downgrade, caps response bytes at 1 MB and allows at most three redirects. Network isolation/egress controls remain recommended because unusual routing can bypass address-based assumptions.
- Robots is requested on each destination hop. 404 and 410 mean no robots file; robots redirects, other error statuses, network failures and unsuitable content fail closed. Matching disallows are enforced conservatively; `Allow` does not override a conflicting disallow. A valid `Crawl-delay` or `Request-rate` extends host cooldown. This can reject pages permitted by a complete RFC 9309 implementation.
- Additive revision `0005_crawler_safety` adds a database control row, leases and host state. At most two leases are granted across processes sharing **the same local database**. Per-host permits prevent overlapping requests, and cooldown is at least one second after completion or a longer robots delay. These limits do not coordinate separate databases or unrelated crawlers. Crashed-worker leases remain until the worker deadline plus a five-second grace; the local clock must be reliable. PostgreSQL, multi-machine deployments, and network filesystems are not verified.
- API reports capacity as 429, timeout as 504, and blocked/failed fetches as 422. Tests verify failed research does not overwrite existing evidence/history. No crawler state is automatically discarded to force a downgrade.

## Exact verification in this workspace

- Complete backend suite: **81 passed, 0 failed, 1 warning in 43.02s**, Linux/Python 3.13, `PYTHONDONTWRITEBYTECODE=1 python -m pytest backend/tests -q -p no:cacheprovider -o faulthandler_timeout=20`. Warning: Starlette/httpx TestClient deprecation.
- Crawler suite after the final worker watchdog change: **21 passed in 10.55s**; cross-process limit tests had also been rerun separately: **2 passed in 1.78s**. The tests use temporary local SQLite, simulated DNS/network responses, worker subprocesses, and process concurrency; they did not contact real sites.
- Complete migration suite: the two 20-test runs listed above, both with zero failures. The previous 18-test version had also passed twice (28.26s and 26.39s).
- Frontend: **4 passed, 0 failed** in jsdom with mocked API responses; `npm run build` passed. No real-browser test.
- Earlier during implementation, a cross-process host pacing test failed and exposed a permit-wait bug; polling the active permit release fixed it and the passing runs above were performed afterward. No test failure is hidden by the final totals.
- PostgreSQL backup behavior is mocked only. No actual PostgreSQL server, `pg_dump`/`pg_restore`, Windows 11, real browser or external-site crawl was tested. Python direct dependencies are pinned, but all transitive Python dependencies are not locked. Independent security review has not been performed.

## Existing workspace preview database

Before the upgrade, `preview.db` was revision `0004_identity_sources`, passed `PRAGMA integrity_check`, and had zero rows in businesses, research history, sources, reviews and import tables. No application writer was running. The first migration attempt created a verified backup but **stopped during preflight** because no administrator token was configured; inspection confirmed the original was unchanged at 0004. A retry with a temporary random environment token created another verified backup, passed rehearsal and migrated the original. Afterward the revision is `0005_crawler_safety`, integrity check is `ok`, and those tables remain empty. The final pre-upgrade backup is `backups/preview-20261031T014139575396Z.db`; the first attempt's backup is also retained. These databases and backups are not included in the source archive. Separate populated temporary-database tests verify preservation, but never replace an independent backup of your real data.

## Files changed in this follow-up

- `backend/app/crawler.py`, `crawl_worker.py`, `crawl_client.py`, `main.py`: manual-fetch safety, persistent limits, process deadline and error handling.
- `backend/migrations/versions/0005_crawler_safety.py`, `backend/manage.py`: additive coordination schema and backup/timeout safeguards.
- `backend/tests/test_crawler.py`, `test_migrations.py`, `test_app.py`, and test support: safety, concurrency, timeouts, migration and preservation checks.
- `README.md`, `docs/ROADMAP.md`, `docs/POSTGRES_DISPOSABLE_TEST.md`, this report, and historical report pointers: instructions and current limitations. React/TypeScript design is retained.

## Required Windows actions (not executed here)

1. Install Python 3.12 and Node.js LTS. Preserve your current `.env` and database. Stop the app and **all** writers and independently copy the existing database, WAL/SHM files if present, and backups to a secure location. Do not replace them with an archive version.
2. In PowerShell at the extracted project root, set up the environment (if not already present), install dependencies, and run the backup-first migration:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
# Set ADMIN_TOKEN in your existing .env; see README. Do not overwrite that file.
.venv\Scripts\python.exe backend\manage.py migrate
```

Check for a successful verified backup, rehearsal and migration. If anything fails, stop and retain the output and all backups; do not stamp or delete data. To change the SQLite copy timeout for this PowerShell session, for example: `$env:SPARKXFLOW_BACKUP_TIMEOUT_SECONDS = '240'`.

3. Run tests/build and start locally:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
cd ..
.venv\Scripts\python.exe backend\run_local.py
```

Open `http://127.0.0.1:8000` on the same PC. Before using PostgreSQL with real data, perform `docs/POSTGRES_DISPOSABLE_TEST.md` and additionally validate multi-process crawler coordination against a disposable PostgreSQL database; that coordination is **not** tested by the listed procedure. Test backup restoration separately.
