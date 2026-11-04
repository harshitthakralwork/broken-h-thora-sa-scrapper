# SparkXFlow — Windows 11 Troubleshooting Guide

Common issues, root causes, and resolutions for running SparkXFlow on Windows 11.

---

## 1. Google Apps Script Returns HTTP 403 / "You Need Access"

### Symptom:
When synchronizing leads to Google Sheets, the dashboard reports:
```
Apps Script authentication failed (HTTP 403): Invalid webhook secret or permissions
```
Or visiting the Web App URL in a browser shows:
```
Title: Access denied
Heading: You need access
Body: Open the document directly to see if requesting access is possible, or switch to an account with access.
```

### Cause:
When deploying the Google Apps Script Web App, Google defaults **"Who has access"** to **"Only myself"** or **"Anyone with a Google Account"**, which forces Google to block external HTTP POST requests from your local machine.

### Fix:
1. Open your Google Sheet > **Extensions** > **Apps Script**.
2. Click the blue **Deploy** button > **New deployment**.
3. Under **Execute as**, select: **`Me (your-email@gmail.com)`**.
4. Under **Who has access**, select: **`Anyone`**.
5. Click **Deploy**.
6. Copy the fresh Web App URL and paste it into SparkXFlow Dashboard under **Google Sheets Sync**.

---

## 2. PowerShell Script Execution Policy Error

### Symptom:
Running `npm run build` or activating `.venv` outputs:
```
File ...\Activate.ps1 cannot be loaded because running scripts is disabled on this system.
```

### Cause:
Windows 11 restricts unsigned PowerShell script execution by default (`Restricted` policy).

### Fix:
Run commands directly through `.venv\Scripts\python.exe` and `npm.cmd`, which completely bypasses the execution policy restriction:
```powershell
# Instead of activating venv:
.\.venv\Scripts\python.exe backend\run_local.py

# Instead of 'npm run build':
npm.cmd run build
```
Or temporarily enable script execution for the current user:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 3. Port 8000 or 5173 is Already in Use

### Symptom:
Starting the backend produces:
```
[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): only one usage of each socket address is normally permitted
```

### Cause:
A previous instance of Python or another web service is already listening on port 8000.

### Fix:
Find and terminate the conflicting process in PowerShell:
```powershell
# Find PID listening on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object OwningProcess

# Stop process by PID (e.g. 1234)
Stop-Process -Id 1234 -Force
```

---

## 4. SQLite Database is Locked

### Symptom:
```
sqlite3.OperationalError: database is locked
```

### Cause:
Multiple processes or background test runners are concurrently writing to `sparkxflow.db`.

### Fix:
1. Ensure only one instance of `run_local.py` is running.
2. If running tests, automated tests run in-memory or in disposable temp files, but if a manual background script crashed holding an open handle, restart PowerShell:
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

---

## 5. Token Authentication Lockout

### Symptom:
Entering the administrator token displays:
```
Too many failed attempts. Try again in 60 seconds.
```

### Cause:
SparkXFlow rate-limits failed authentication attempts: after 10 failed logins, the IP is locked out for 60 seconds.

### Fix:
Wait 60 seconds. Then double-check your exact `ADMIN_TOKEN` inside `.env`:
```powershell
Get-Content .env | Select-String "ADMIN_TOKEN="
```
Copy the token string carefully without any trailing spaces or quotation marks.

