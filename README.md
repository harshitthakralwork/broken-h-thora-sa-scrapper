# SparkXFlow Lead Intelligence Engine

An India-first, AI-powered autonomous lead discovery, research qualification, contact intelligence, CRM, and human-supervised outreach platform built specifically for the **SparkXFlow Agency**.

---

## Key Capabilities

1. **Multi-Source Autonomous Lead Discovery:**
   - **Wikidata SPARQL Knowledge Graph:** Live discovery for real Indian enterprises and commercial entities (CC0 1.0).
   - **OpenStreetMap Overpass:** Real geospatial commercial establishment discovery across Indian metros.
   - **OutLead Bulk Maps Engine:** Cartesian multi-city, multi-category batch discovery with persistent progress tracking and branch deduplication.
   - **Structured CSV Import:** Seamless ingestion of existing business directories with automatic provenance and duplicate detection.

2. **Evidence-Based Lead Intelligence (9 Services):**
   - Independent opportunity scoring for all 9 SparkXFlow agency services:
     1. Website Development
     2. Web Applications
     3. AI Automation
     4. E-commerce Development
     5. SaaS Development
     6. SEO and Digital Marketing
     7. Mobile Applications
     8. CRM and Business Automation
     9. Video Editing
   - Decoupled **Business Quality** (10–95) and **Conversion Potential** (15–90) scores.
   - Every score is backed by observable technical facts (viewport, CMS signatures, forms, checkout presence, media).
   - Strict absence guards: absence of a chatbot or video does **not** invent customer intent.

3. **Contact Intelligence & Decision-Maker Discovery:**
   - Discovers public founders, CEOs, managing directors, and key operational decision-makers.
   - Extracts business emails and verified phone numbers from public websites and official registers.
   - Strict provenance: never mark guessed emails as verified; unverified emails remain `unverified_public`.

4. **CRM & Sales Pipeline Management:**
   - Kanban pipeline stages: `uncontacted`, `qualified`, `meeting_scheduled`, `proposal_sent`, `negotiation`, `won`, `lost`.
   - Bulk lead selection, multi-tagging, and stage transitions.
   - Inbound reply simulation, auto-detection of unsubscribes, and automated suppression list updates.

5. **Human-in-the-Loop Outreach & Email Safety:**
   - **Global Sending Kill-Switch:** Defaults to `EMAIL_SENDING_ENABLED=false`.
   - **Cryptographic Approval Sealing:** Every outgoing email requires one-by-one human approval. Approvals bind cryptographically (SHA-256) to the exact recipient, subject, and body text.
   - Editing an approved email immediately revokes prior approval.

6. **Hardened Google Sheets Synchronization Bridge:**
   - Real-time lead synchronization with Google Sheets via dedicated Google Apps Script Web App.
   - Authenticated via dedicated `SHEETS_WEBHOOK_SECRET` (constant-time verification; never reuses `ADMIN_TOKEN`).
   - Strict target spreadsheet (`1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk`) and GID (0) enforcement.
   - Preserves manual sales notes, deal stages, and rep comments in Columns 17+ (`Q` onward).
   - Deterministic upsert on Column A (`Business ID`) prevents duplicate rows during sync or retries.

7. **Database Authority & Safe Migrations:**
   - Local SQLite (`sparkxflow.db`) serves as the single source of truth.
   - Backup-first Alembic migrations (`backend/manage.py migrate`) verify integrity before and after applying schema updates.

---

## Documentation Guides

- 📘 [**SETUP_WINDOWS.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/SETUP_WINDOWS.md): Complete Windows 11 setup and launch instructions for beginners.
- ⚙️ [**ENVIRONMENT_CONFIGURATION.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/ENVIRONMENT_CONFIGURATION.md): Detailed reference for every `.env` setting.
- 📊 [**GOOGLE_SHEETS_DEPLOYMENT.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/GOOGLE_SHEETS_DEPLOYMENT.md): Google Apps Script setup, authorization, and Web App deployment guide.
- 🌐 [**API_PROVIDER_STATUS.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/API_PROVIDER_STATUS.md): Truthful classification and audit of all discovery connectors.
- 🧪 [**TEST_RESULTS.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/TEST_RESULTS.md): Full test logs (160 backend tests, Vitest suite, Vite build, live discovery test).
- 🛠️ [**TROUBLESHOOTING.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/TROUBLESHOOTING.md): Fixes for common Windows 11 port, execution policy, and permission issues.
- 📋 [**PROJECT_COMPLETION_REPORT.md**](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/PROJECT_COMPLETION_REPORT.md): Final master audit and production readiness signoff.

---

## Quick Start on Windows 11

```powershell
# 1. Navigate to project directory
cd C:\Users\minem\Downloads\workspace-01a18f94-4002-799c-adfe-a9090e1446d3\sparkxflow-crawler-safety-update\sparkxflow-lead-engine

# 2. Start the unified production server
.\.venv\Scripts\python.exe backend\run_local.py
```

Open **`http://127.0.0.1:8000`** in your browser and enter your `ADMIN_TOKEN` from `.env`.
