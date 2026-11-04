# Previous verification (before shared-domain migration 0004)

> Historical snapshot only. Later migrations and crawler changes are documented in `CRAWLER_SAFETY_REPORT.md`.

For the current identity update, see `SHARED_DOMAIN_REPORT.md`; this document records the prior verification baseline.

# Verification report

## Named migration test

`test_incompatible_database_is_not_stamped` passed in isolation in the Linux sandbox before and after changes; the reported Windows failure could not be reproduced here, and its exact cause remains unknown without the Windows error output. The test still checks the incompatibility diagnosis and that the database is not stamped. It now reports captured subprocess output on an unexpected error. The migration tests use encoded SQLAlchemy SQLite URLs, UTF-8 subprocess streams, isolated temporary backup directories and independent databases, reducing path/encoding and test-order problems. An explicit non-ASCII, space and `#` path case was tested on Linux; actual Windows path behavior remains unverified.

## SQLite

Automated disposable SQLite tests cover fresh, unversioned legacy, revisions 0001, 0002 and current 0003, idempotent upgrades, malformed data/schema and protected downgrade paths. A SQLite migration now starts an explicit transaction for DDL; failed multi-revision downgrades roll back intermediate schema changes in the tested cases. These tests do not establish safety for arbitrary user-modified databases or concurrent writers; stop writers, preserve a separate backup and follow the migration command. Existing workspace databases were not upgraded during this verification pass.

## PostgreSQL

Backup command construction, conflicting environment rejection and dump-failure handling are tested with mocks only. No PostgreSQL server, pg_dump, pg_restore, Docker, real PostgreSQL upgrade or restore was available in the sandbox. Database URL query parameters are rejected; the tool requires an explicit loopback host, port, user and database and refuses ambient libpq connection overrides that could change the backup target. The separate `POSTGRES_DISPOSABLE_TEST.md` procedure describes a fresh and legacy migration plus restore using disposable data; it has not been executed here. It does not validate every deployment or prove production backup safety.

## Duplicate reviews

Possible matches are retained, with original incoming fields and matching references; no automatic merge is implemented. Review resolution now atomically claims a pending record and performs any explicit separate-lead creation in the same transaction. Tests cover retained reviewed candidates, domain conflicts and concurrent requests. Shared-domain candidates remain review-only because the original domain uniqueness constraint is unchanged. A marked-reviewed candidate is retained but cannot be reopened through the current UI.

## Research crawler review

There is an eight-second socket-operation timeout, a one-megabyte response limit, up to four page hops and a two-research-request semaphore per process. These are not a total deadline: DNS resolution may block and a slow peer can extend a response by sending data slowly. The semaphore is not shared across processes. There is no per-host interval, robots `Crawl-delay` enforcement, global quota or persistent rate state, and no independent security review. Continue only manual, permitted research; do not enable autonomous discovery or scale crawling before these controls are designed, implemented and tested. Robots.txt does not by itself grant legal permission.

## Frontend and environment

Frontend tests use jsdom and mocked API responses, not a real browser. A production build is tested. The clean Python virtual environment test was performed on Linux with Python 3.13, not Windows 11/Python 3.12. Direct Python dependencies are pinned to the tested versions but transitive dependencies are not fully locked. The test run produced the Starlette/httpx deprecation warning; npm install also produced a deprecation warning for whatwg-encoding. No real network crawling, browser automation or PostgreSQL server was tested in this verification pass.

## Final commands and outcomes in this sandbox

- Fresh Python 3.13 virtual environment: installed `backend/requirements.txt` and ran `python -m pytest backend/tests -q -p no:cacheprovider`: **42 passed, 0 failed**, one Starlette/httpx deprecation warning. PostgreSQL checks among these are mocked.
- Frontend: `npm ci --no-audit --no-fund`, `npm test`: **2 passed, 0 failed**, and `npm run build`: **passed**. The npm install reported a `whatwg-encoding` deprecation warning.
- The named incompatibility test passed in isolation; no Windows reproduction was available.
- No PostgreSQL, `pg_dump`/`pg_restore`, Windows 11, Python 3.12 or real-browser run was performed.
