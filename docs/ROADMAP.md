# Roadmap after crawler safety

The React/TypeScript and FastAPI foundation remains local-only, with manual research only. See `CRAWLER_SAFETY_REPORT.md` for current verification and limitations.

1. Reproduce the previously reported migration hang on the affected Linux environment; collect diagnostics and confirm the bounded/isolated suite there. Test the Windows setup and a real browser.
2. Verify all migrations, shared-domain decisions, crawler coordination, PostgreSQL backup and restore against a disposable local PostgreSQL server. Add CI and dependency locking.
3. Obtain independent security and lawful-use review of manual research, including unusual routing, robots handling and process/clock failure. Validate evidence schema and deploy appropriate network egress restrictions.
4. Only after this phase, separately evaluate compliant discovery connectors, persistent jobs and scoped integrations, each with authorization, quotas and privacy review.
5. Treat outreach as a separate milestone: no sending until recipient- and version-specific approval, global suppression, eligibility, audit logging and duplicate-send protections are implemented and tested.

No AI scoring, autonomous scraping, email sending or paid service has been introduced in this phase.
