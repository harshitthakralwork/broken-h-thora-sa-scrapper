# SparkXFlow Lead Intelligence Engine — Windows 11 Setup Guide

A complete, beginner-friendly guide to running SparkXFlow on Windows 11 for internal agency operations.

---

## 1. Prerequisites Check

Before starting, make sure you have the following installed on your Windows 11 PC:

1. **Python 3.11 or 3.12** (From [python.org](https://www.python.org/downloads/)).
   > *Important during installation:* Check the box **"Add python.exe to PATH"**.
2. **Node.js LTS (v20 or v22)** (From [nodejs.org](https://nodejs.org/)).
3. **PowerShell** (Built-in on Windows 11).

Verify your installations in PowerShell:
```powershell
python --version
node --version
npm.cmd --version
```

---

## 2. Initial Setup (One-Time)

Open PowerShell and navigate to the project directory:

```powershell
cd C:\Users\minem\Downloads\workspace-01a18f94-4002-799c-adfe-a9090e1446d3\sparkxflow-crawler-safety-update\sparkxflow-lead-engine
```

### Step 2.1 — Python Virtual Environment
If `.venv` does not already exist, create and activate it:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### Step 2.2 — Environment Configuration (.env)
Check that your `.env` file exists and has an `ADMIN_TOKEN`:
```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```
If you need a new secure token, generate one using:
```powershell
.\.venv\Scripts\python.exe -c "import secrets; print('ADMIN_TOKEN=' + secrets.token_urlsafe(32))"
```

### Step 2.3 — Frontend Dependencies & Production Build
```powershell
cd frontend
npm.cmd install
npm.cmd run build
cd ..
```
The production bundle will be created at `frontend\dist`.

### Step 2.4 — Database Migration Verification
Run the backup-first migration manager to ensure your SQLite database is on the latest schema:
```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
```
This safely creates an integrity-verified backup in `backups\` before applying any schema updates.

---

## 3. Daily Launch Instructions

### Option A: Running Production Server (Recommended)
This starts the unified FastAPI backend serving the pre-built React frontend:

```powershell
# In PowerShell:
.\.venv\Scripts\python.exe backend\run_local.py
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:8000`**

Log in using your `ADMIN_TOKEN` from `.env`.

### Option B: Running Development Mode
If you are developing or modifying frontend React components with live hot-reloading:

**Terminal 1 (Backend API):**
```powershell
.\.venv\Scripts\python.exe backend\run_local.py
```

**Terminal 2 (Frontend Dev Server):**
```powershell
cd frontend
npm.cmd run dev
```
Open your browser at 👉 **`http://localhost:5173`**.

---

## 4. How to Back Up Your SQLite Database

Your business leads, qualified contacts, and pipeline data reside in `sparkxflow.db`.

### Automatic Backup via Manage Script:
```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
```
This automatically backs up the database to `backups\sparkxflow-<timestamp>.db` and executes `PRAGMA integrity_check`.

### Manual Fast Snapshot:
```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect('sparkxflow.db'); b=sqlite3.connect('backups/manual_snapshot.db'); s.backup(b); b.close(); s.close(); print('Backup completed safely!')"
```

---

## 5. Running the Test Suite

To verify that the entire platform is functioning properly with zero regressions:

### Backend Test Suite (160 tests):
```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\ -v
```

### Frontend Vitest Suite:
```powershell
cd frontend
npm.cmd test
cd ..
```

---

## 6. Safe Shutdown

Press **`Ctrl + C`** in your PowerShell window to cleanly shut down the server. SQLite database locks are automatically released upon process termination.

