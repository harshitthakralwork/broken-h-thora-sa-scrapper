# Shared-domain identity update

> Historical report for 0004. For current migration, crawler safety and verification status, see `CRAWLER_SAFETY_REPORT.md` and `README.md`.

## Behavior

- Business records use their own IDs. A non-unique `business_domains` association supports multiple companies or locations with the same domain. The old unique `businesses.domain` column is left untouched for compatibility; new records use the new association and leave that legacy field null. The API continues to expose the normalized domain.
- An exact **field match** requires matching normalized name, domain and nonempty location. It is a review signal, not verified business identity. Other matches are flagged as possible. No match is merged automatically.
- An administrator can explicitly resolve a candidate as the same business, a separate business, a branch, a subsidiary, or a parent. Branch and subsidiary relationships record direction. Same-business decisions attach a source to the existing business; the incoming candidate and decision remain in history. Existing active leads are never silently merged or deleted.
- A database-backed identity lock serializes matching and creation; review resolution is claimed atomically. A review previously marked `reviewed` can be reopened without deleting its prior events.
- Each accepted CSV batch retains its original CSV, parsed candidates, status and errors. The source attached to a business is retained with its import/review links. Invalid parsed rows are retained as invalid. Malformed CSV, a request over 100,000 characters, or a batch over 500 rows is rejected before acceptance; the original input must be corrected or split and retried.

## Migration

Migration `0004_identity_sources` adds new tables and indexes; it does not rebuild or delete the original business, review or research tables. Existing sources are copied from their original records, and existing domains are indexed. A backup-first SQLite rehearsal is required through `backend/manage.py migrate`. The downgrade refuses to remove populated provenance, domain, decision or import data. Older CSV candidates skipped before import history existed cannot be recovered from this migration.

## Limitations

- No live PostgreSQL migration or Windows 11 run was performed in this sandbox. The disposable PostgreSQL verification procedure remains necessary; the current head is `0005_crawler_safety`.
- Frontend tests use mocked APIs and jsdom rather than a real browser. The app remains local-only.
- At the time of this report, crawler total deadlines and per-host limits remained unresolved; later work is described in `CRAWLER_SAFETY_REPORT.md`. No autonomous discovery, AI scoring or email functionality was added.

## Final verification in the supplied sandbox

- Backend: **56 passed, 0 failed** on Linux/Python 3.13, including shared-domain branch tests, same-business provenance, parent/subsidiary direction, CSV candidate preservation, concurrent matching/resolution, and migration of populated 0003 SQLite data. One Starlette/httpx deprecation warning remains.
- Frontend: **4 passed, 0 failed** in jsdom with mocked API responses; the production build passed. This is not a real-browser test.
- The workspace preview SQLite database was backed up before migrating to 0004; it contained no business, review or research rows. Separate temporary migration tests verified preservation of populated legacy records.
- The existing tests that expected shared domains to be rejected and a partial import of 501 rows initially failed after the behavior changed; they were updated to assert explicit review and safe whole-batch rejection. One new frontend test initially failed due to whitespace-normalized text matching; it was corrected and the final suite passed.
- PostgreSQL, Windows 11 and real-browser testing were not performed. The `pg_dump` tests remain mocked.
