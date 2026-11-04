# SparkXFlow Lead Intelligence Engine — System Architecture & User Guide

SparkXFlow is a production-grade, local-first lead discovery, intelligence scoring, decision-maker research, and email outreach platform developed for SparkXFlow Agency.

---

## 1. Core Architecture & Four Intelligence Engines

```
                    ┌───────────────────────────────────────────────┐
                    │        SparkXFlow React + TS Dashboard        │
                    │         (11 Interactive Platform Views)       │
                    └───────────────────────┬───────────────────────┘
                                            │ HTTP / JSON API (Bearer Auth)
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │               FastAPI Backend                 │
                    │        (Bound strictly to 127.0.0.1:8000)     │
                    └───────┬───────────────┬───────────────┬───────┘
                            │               │               │
         ┌──────────────────▼──┐     ┌──────▼────────┐   ┌──▼──────────────────┐
         │ Engine A & B:       │     │ Engine C:     │   │ Engine D:           │
         │ Market & Lead Intel │     │ Contact Intel │   │ Sales & Outreach    │
         ├─────────────────────┤     ├───────────────┤   ├─────────────────────┤
         │ • Hypotheses Gen    │     │ • Decision-   │   │ • AI Personalized   │
         │ • Modular Connectors│     │   Maker Match │     Draft Generation    │
         │   (Directory, Web,  │     │ • RFC & DNS   │   │ • SHA256 Approval   │
         │    CSV Import)      │     │   Validation  │     Tamper Integrity    │
         │ • Lead Normalizer   │     │ • Verification│   │ • Strict Human Gate │
         │ • Service Scoring   │     │   Tiers       │   │ • Follow-up Cadence │
         │   (9 Agency Offer-  │     │ • Manual Lead │   │ • Inbox Sync &      │
         │    ings, 0-100)     │     │   Overrides   │     Classification    │
         └──────────┬──────────┘     └───────┬───────┘   └──────────┬──────────┘
                    │                        │                      │
                    └────────────────────────┼──────────────────────┘
                                             │
                    ┌────────────────────────▼──────────────────────┐
                    │               SQLite / PostgreSQL             │
                    │         (Alembic Migration Architecture)      │
                    └────────────────────────┬──────────────────────┘
                                             │
                    ┌────────────────────────▼──────────────────────┐
                    │          Integrations & Automation            │
                    │ • Google Sheets 2-Way Sync (Apps Script Hook) │
                    │ • n8n Webhook Workflow Dispatcher             │
                    │ • Global Autonomous Kill Switch               │
                    └───────────────────────────────────────────────┘
```

---

## 2. Nine Core Agency Services

The platform discovers business opportunities and computes evidence-backed fit scores (0–100) across all 9 SparkXFlow services:

1. **Website Development**: Evaluates viewport meta responsiveness, outdated HTML constructs, slow assets, and mobile optimization.
2. **Web Application Development**: Evaluates missing client portals, interactive apps, and customer login mechanisms.
3. **AI Automation**: Identifies manual inquiry capture, absence of conversational booking, and unstructured email workflows.
4. **E-commerce Development**: Analyzes catalog existence without modern cart flows, missing payment gate indicators, or legacy stores.
5. **SaaS Development**: Discovers bespoke software opportunities for workflows presently handled by static spreadsheets.
6. **SEO and Digital Marketing**: Analyzes meta tags, open graph metadata, structured JSON-LD schemas, and heading hierarchies.
7. **Mobile Application Development**: Observes missing PWA manifestations, mobile viewport gaps, and desktop-constrained tools.
8. **CRM and Business Automation**: Identifies unlinked contact forms, manual lead capture, and missing pipeline synchronization.
9. **Video Editing**: Detects media-rich landing pages lacking engaging motion graphics, explainer videos, or modern WebM/MP4 presentations.

---

## 3. Engine D: Strict Human Approval Center & Tamper Protection

SparkXFlow enforces a **Zero-Accidental-Outreach** safety guarantee:

- **Global Sending Toggle**: Outbound email transmission is globally disabled by default (`sending_enabled: false`).
- **Cryptographic Hash Verification**: When an email draft is reviewed and approved, a SHA-256 hash is computed over the normalized recipient email, subject line, and message body.
- **Instant Revocation on Edit**: Any modification to an approved message (subject, body, or recipient) immediately invalidates the hash, resetting the message status back to `pending_approval` and requiring re-approval.
- **Suppression Safeguards**: Hard suppression list and bounce/unsubscribe rules automatically halt outbound cadence and suppress future emails to that address or domain.
- **Follow-up Cadence**: Automated sequence intervals (Day 3, Day 7, Day 14) are created as individual tasks, and **each follow-up step requires explicit human approval** before delivery.

---

## 4. Google Sheets & n8n Integrations

- **Google Sheets Working View**:
  - Live 2-way sync bridge using a Google Apps Script Webhook.
  - Automatically exports leads, research scores, assigned services, and contact information into your active Google Sheet.
  - In local development mode without a configured webhook URL, the engine simulates the synchronization safely and reports row preparation status.
- **n8n Automation Dispatcher**:
  - Fires structured event webhooks (`lead.discovered`, `qualification.completed`, `outreach.approved`, `reply.received`) to trigger custom n8n workflows.

---

## 5. Quick Start & Verification

### Launching the Application
```powershell
# From the repository root:
.\.venv\Scripts\python.exe backend\run_local.py
```

### Accessing the Dashboard
- URL: **http://127.0.0.1:8000**
- Admin Token: Retrieved from your `.env` file (`ADMIN_TOKEN`).

### Running the Complete Test Suite
```powershell
# Backend tests (87 tests, 100% pass):
.\.venv\Scripts\pytest backend/tests -q

# Frontend tests (5 tests, 100% pass):
npm.cmd --prefix frontend test -- --run
```

