# SparkXFlow — Google Sheets Apps Script Deployment Guide

A step-by-step walkthrough for deploying the synchronization bridge into your target spreadsheet.

---

## Target Spreadsheet Specification
- **Target Spreadsheet:** [https://docs.google.com/spreadsheets/d/1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk/edit](https://docs.google.com/spreadsheets/d/1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk/edit)
- **Target Spreadsheet ID:** `1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk`
- **Target Sheet GID:** `0` (First Tab)

---

## Step 1: Open Apps Script Editor
1. Open the spreadsheet in Google Chrome.
2. In the top menu, click **Extensions** > **Apps Script**.
3. A new tab will open with the code editor.

---

## Step 2: Paste the Sync Script
1. Delete any existing sample code (`function myFunction() { ... }`).
2. Open [`backend/app/integrations/google_sheets_sync.gs`](file:///c:/Users/minem/Downloads/workspace-01a18f94-4002-799c-adfe-a9090e1446d3/sparkxflow-crawler-safety-update/sparkxflow-lead-engine/backend/app/integrations/google_sheets_sync.gs) from this project, copy the entire code, and paste it into the Apps Script editor.
3. Press **`Ctrl + S`** (or click the disk save icon).

---

## Step 3: Configure Your Webhook Secret
The script requires an authentication secret to ensure that only your SparkXFlow dashboard can sync data to your sheet.

1. In the toolbar, locate the function dropdown (it may show `myFunction` or `No functions`).
2. Select **`setupWebhookSecret`**.
3. Click the **`▷ Run`** button.
4. Google will ask for authorization on the first run:
   - Click **Review permissions**.
   - Choose your Google Account (`harshitthakralworks@gmail.com`).
   - Click **Advanced** (at the bottom-left of the popup).
   - Click **Go to Untitled project (unsafe)**.
   - Click **Allow**.
5. Check the **Execution Log** at the bottom:
   ```
   ✅ WEBHOOK_SECRET successfully saved to Script Properties (length: 32).
   ```

---

## Step 4: Deploy as a Web App

> [!IMPORTANT]
> To allow your local SparkXFlow engine to transmit data over HTTP, you must select **"Anyone"** under "Who has access". Because you configured a shared `WEBHOOK_SECRET` in Step 3, unauthorized callers cannot alter your sheet.

1. In the top-right corner, click the blue **Deploy** button > **New deployment**.
2. Click the **Gear icon (⚙️ Select type)** on the left and choose **Web app**.
3. Set the configuration fields:
   - **Description:** `SparkXFlow Lead Intelligence Sync`
   - **Execute as:** `Me (harshitthakralworks@gmail.com)`
   - **Who has access:** `Anyone`
4. Click **Deploy**.
5. Google will display a **Web app URL**:
   ```
   https://script.google.com/macros/s/AKfycb.../exec
   ```
6. Click **Copy** to copy this URL.

---

## Step 5: Connect in SparkXFlow Dashboard

1. Start your SparkXFlow dashboard (`http://localhost:5173` or `http://127.0.0.1:8000`).
2. Navigate to **Google Sheets Sync** (Tab 9).
3. In the **Apps Script Webhook Integration** card:
   - Paste the **Web app URL**.
   - Enter your **Webhook Secret** (or set `SHEETS_WEBHOOK_SECRET` in `.env`).
   - Click **Save Webhook Config**.
4. Click **Sync Leads to Sheets Now**.
   - The status will change to **Connected**.
   - All discovered and qualified leads will be synced to your sheet in columns A–P!

---

## Data Protection Safeguards
- **Column Protection:** The script only updates columns 1 through 16 (`A` through `P`). Any custom columns you create in **Column 17 onward** (`Q`, `R`, `S`... e.g. "Sales Stage", "Rep Notes", "Next Call Date") are **100% preserved and never overwritten**.
- **Deterministic Upsert:** Column A (`Business ID`) is indexed. Syncing multiple times or retrying will **update existing rows in-place** and will **never create duplicate rows**.

