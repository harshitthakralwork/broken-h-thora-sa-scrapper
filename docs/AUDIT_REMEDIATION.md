# Engineering audit remediation — delivery notes

## Implemented

- Explicit Alembic baseline and additive revisions; backup-first migration tool; SQLite preflight on a disposable copy; stop on an unknown or incompatible schema. Original baseline downgrade is blocked; later table downgrades are blocked when data exists.
- Preserved existing business IDs and reports; migrated legacy raw reports into research history without replacing the original values.
- Duplicate-review records preserve incoming data and matches. No automatic merge. Same-domain lead creation remains constrained by the original unique index.
- Removed misleading numeric opportunity assessments from display and export. Single-page findings are technical observations, not evidence of demand. Raw legacy reports remain preserved.
- Loopback-only supported launcher and peer/host/origin checks; token placeholder rejection and local failure throttling. No outgoing email route.
- Strict CSV parsing, row cap, formula-aware export, safe error responses, request IDs, structured logs, API pagination, frontend login validation and history review.
- SQLite migration and safety tests; simulated-DOM frontend tests with mocked backend responses. The local HTTP smoke check was performed against a loopback-bound server.

## Known limitations and follow-up

- PostgreSQL migration and dump/restore paths have not been exercised in the sandbox: Docker, PostgreSQL and pg_dump were unavailable. Test them with a disposable local server before moving real data.
- The migration tool will not stamp unknown or divergent schemas. SQLite rehearses upgrades on a copy; PostgreSQL DDL relies on a successful backup and its transactional behavior. Restore-test backups separately. PostgreSQL URL query parameters and non-local servers are deliberately unsupported by the backup tool.
- Shared-domain candidates can now be resolved as separate records or explicit relationships through migration `0004_identity_sources`; see `SHARED_DOMAIN_REPORT.md`. Earlier unrecorded skipped imports cannot be recovered.
- A completely malformed legacy JSON report is preserved but cannot be interpreted by the dashboard. Some partially structured legacy reports are similarly withheld from display.
- The manual crawler now uses killable-worker deadlines and shared-database per-host/global coordination; see `CRAWLER_SAFETY_REPORT.md`. Robots handling and SSRF defenses still require independent review before expanding use.
- Frontend tests mock API responses; no real browser end-to-end suite was available. No real website or production PostgreSQL was used in testing.
- The single administrator token is suitable only for a trusted local user. There are no roles, audit trail, secret vault or deployment controls for remote use.
- Python dependency ranges are not a fully locked environment. The installed Starlette test client emitted a deprecation warning about its httpx backend.
- This workspace was not a Git repository, so Git history and previously committed secrets could not be audited. Review your actual repository and history independently before pushing.
