/**
 * ============================================================================
 * SparkXFlow Lead Intelligence Engine — Google Sheets Synchronization Bridge
 * ============================================================================
 * 
 * Target Spreadsheet:
 *   ID:  1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk
 *   GID: 0
 * 
 * Security & Data Integrity Features:
 * 1. Enforces exact TARGET_SPREADSHEET_ID and TARGET_SHEET_GID. No arbitrary sheet access.
 * 2. Rejects request if WEBHOOK_SECRET is missing, empty, or mismatched (constant-time check).
 * 3. Never logs, prints, or exposes the secret in responses, logs, or sheet cells.
 * 4. Exact GID verification with NO silent fallback.
 * 5. Column 1 Header validation to prevent corrupting mismatched sheets.
 * 6. Preserves columns 17+ (Q onward). Custom sales stages, rep notes, call dates untouched.
 * 7. Deterministic upsert on Column A (Business ID). Retries will never duplicate rows.
 * 
 * HTTP Status Limitation Note (Google Apps Script):
 * Google Apps Script ContentService does not support arbitrary HTTP response codes (such as
 * 400, 401, 403, 404). ContentService outputs always return HTTP 200 (via a 302 redirect).
 * Therefore, authorization, validation, and error states are communicated via structured
 * JSON envelopes with `success: false`, `status: "unauthorized"|"forbidden"|"error"`, and
 * `error: "<details>"`. The SparkXFlow backend strictly verifies `response.success === true`.
 * ============================================================================
 */

// Target spreadsheet configuration (Strictly enforced)
var TARGET_SPREADSHEET_ID = "1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk";
var TARGET_SHEET_GID = 0;

// Standard headers for columns 1 to 16 (Columns A through P)
var STANDARD_HEADERS = [
  "Business ID",
  "Business Name",
  "Website",
  "Domain",
  "Industry",
  "Sub-Industry",
  "City",
  "Country",
  "Top Recommended Service",
  "Opportunity Score",
  "Quality Score",
  "Contacts",
  "Discovery Source",
  "Discovered At",
  "Last Synced At",
  "SparkXFlow Status"
];

/**
 * Returns the target sheet tab matching exact GID 0.
 * NEVER silently falls back to another sheet. Returns null if not found.
 */
function getTargetSheet(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === TARGET_SHEET_GID) {
      return sheets[i];
    }
  }
  return null;
}

/**
 * Retrieves the webhook secret configured in Script Properties.
 */
function getWebhookSecret() {
  return PropertiesService.getScriptProperties().getProperty("WEBHOOK_SECRET") || "";
}

/**
 * Constant-time string comparison to mitigate timing attacks.
 */
function constantTimeCompare(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  var lenA = a.length;
  var lenB = b.length;
  var mismatch = lenA === lenB ? 0 : 1;
  var maxLen = Math.max(lenA, lenB);
  for (var i = 0; i < maxLen; i++) {
    var charA = i < lenA ? a.charCodeAt(i) : 0;
    var charB = i < lenB ? b.charCodeAt(i) : 0;
    mismatch |= charA ^ charB;
  }
  return mismatch === 0 && lenA === lenB;
}

/**
 * Securely configures the webhook secret in Script Properties.
 * SECURITY: Never logs, prints, or returns the secret string.
 */
function setupWebhookSecret(secretToSave) {
  if (!secretToSave || String(secretToSave).trim() === "") {
    Logger.log("❌ Error: Cannot set an empty WEBHOOK_SECRET.");
    return false;
  }
  var cleanSecret = String(secretToSave).trim();
  PropertiesService.getScriptProperties().setProperty("WEBHOOK_SECRET", cleanSecret);
  Logger.log("✅ WEBHOOK_SECRET successfully saved to Script Properties (length: " + cleanSecret.length + ").");
  return true;
}

/**
 * Handles incoming POST requests from SparkXFlow Lead Engine.
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({
        success: false,
        status: "bad_request",
        error: "Missing request body"
      });
    }

    var data;
    try {
      data = JSON.parse(e.postData.contents);
    } catch (parseErr) {
      return jsonResponse({
        success: false,
        status: "bad_request",
        error: "Malformed JSON payload: " + parseErr.message
      });
    }

    // 1. Mandatory Secret Verification
    var expectedSecret = getWebhookSecret();
    if (!expectedSecret || expectedSecret.trim() === "") {
      return jsonResponse({
        success: false,
        status: "unauthorized",
        error: "Server configuration error: WEBHOOK_SECRET is not configured in Apps Script Properties"
      });
    }

    var providedSecret = (data.secret || "").trim();
    if (!providedSecret || !constantTimeCompare(providedSecret, expectedSecret)) {
      return jsonResponse({
        success: false,
        status: "unauthorized",
        error: "Unauthorized: Invalid or missing webhook secret"
      });
    }

    // 2. Strict Spreadsheet Identity Enforcement
    if (data.sheet_id && String(data.sheet_id).trim() !== TARGET_SPREADSHEET_ID) {
      return jsonResponse({
        success: false,
        status: "forbidden",
        error: "Forbidden: Incoming sheet_id does not match the authorized TARGET_SPREADSHEET_ID"
      });
    }

    if (data.sheet_gid !== undefined && data.sheet_gid !== null && Number(data.sheet_gid) !== TARGET_SHEET_GID) {
      return jsonResponse({
        success: false,
        status: "forbidden",
        error: "Forbidden: Incoming sheet_gid (" + data.sheet_gid + ") does not match authorized TARGET_SHEET_GID (" + TARGET_SHEET_GID + ")"
      });
    }

    // 3. Open Authorized Spreadsheet
    var ss;
    try {
      ss = SpreadsheetApp.openById(TARGET_SPREADSHEET_ID);
    } catch (openErr) {
      return jsonResponse({
        success: false,
        status: "error",
        error: "Could not open target spreadsheet: " + openErr.message
      });
    }

    // 4. Exact GID verification (No silent fallback)
    var sheet = getTargetSheet(ss);
    if (!sheet) {
      return jsonResponse({
        success: false,
        status: "not_found",
        error: "Target sheet tab with GID " + TARGET_SHEET_GID + " was not found in spreadsheet."
      });
    }

    var records = data.records;
    if (!Array.isArray(records)) {
      return jsonResponse({
        success: false,
        status: "bad_request",
        error: "Expected 'records' array in payload"
      });
    }

    var lastRow = sheet.getLastRow();
    var lastCol = sheet.getLastColumn();

    // 5. Header Validation and Initialization
    if (lastRow === 0 || lastCol === 0) {
      // Empty sheet: Initialize standard headers
      sheet.getRange(1, 1, 1, STANDARD_HEADERS.length).setValues([STANDARD_HEADERS]);
      sheet.getRange(1, 1, 1, STANDARD_HEADERS.length).setFontWeight("bold").setBackground("#f3f4f6");
      lastRow = 1;
    } else {
      // Sheet has data: Validate existing headers in row 1
      var headerRange = sheet.getRange(1, 1, 1, Math.min(Math.max(lastCol, 1), STANDARD_HEADERS.length));
      var existingHeaders = headerRange.getValues()[0];
      var firstHeader = String(existingHeaders[0] || "").trim().toLowerCase();
      
      // If row 1 is completely empty, populate headers
      if (!firstHeader && existingHeaders.every(function(h) { return !String(h).trim(); })) {
        sheet.getRange(1, 1, 1, STANDARD_HEADERS.length).setValues([STANDARD_HEADERS]);
        sheet.getRange(1, 1, 1, STANDARD_HEADERS.length).setFontWeight("bold").setBackground("#f3f4f6");
      } else if (firstHeader !== "business id" && firstHeader !== "business_id" && firstHeader !== "id") {
        return jsonResponse({
          success: false,
          status: "invalid_headers",
          error: "Header validation failed: Column A header must be 'Business ID'. Found: '" + existingHeaders[0] + "'. Write aborted to protect existing data."
        });
      }
    }

    // 6. Index Existing Business IDs (Column A) for Deterministic Upsert
    var idToRowMap = {};
    if (lastRow > 1) {
      var idValues = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (var r = 0; r < idValues.length; r++) {
        var existingId = String(idValues[r][0] || "").trim();
        if (existingId && !idToRowMap[existingId]) {
          idToRowMap[existingId] = r + 2; // 1-based sheet row index
        }
      }
    }

    var updatedCount = 0;
    var appendedCount = 0;
    var syncTimestamp = data.synced_at || new Date().toISOString();
    var seenInCurrentSync = {};

    // 7. Upsert Records (Columns 1 to 16 ONLY)
    for (var i = 0; i < records.length; i++) {
      var item = records[i];
      if (!item || typeof item !== "object") continue;
      var bid = String(item.business_id || "").trim();
      if (!bid) continue;

      var rowValues = [
        bid,                                        // Col 1: Business ID
        item.name || "",                            // Col 2: Business Name
        item.website || "",                         // Col 3: Website
        item.domain || "",                          // Col 4: Domain
        item.industry || "",                        // Col 5: Industry
        item.sub_industry || "",                    // Col 6: Sub-Industry
        item.city || "",                            // Col 7: City
        item.country || "",                         // Col 8: Country
        item.top_recommended_service || "",        // Col 9: Top Recommended Service
        item.opportunity_score !== undefined ? item.opportunity_score : 0, // Col 10: Score
        item.quality_score !== undefined ? item.quality_score : 0,         // Col 11: Quality
        item.contacts || "",                        // Col 12: Contacts
        item.discovery_source || "",                // Col 13: Source
        item.discovered_at || "",                   // Col 14: Discovered At
        syncTimestamp,                              // Col 15: Last Synced At
        "Active"                                    // Col 16: SparkXFlow Status
      ];

      var targetRow = idToRowMap[bid];
      if (targetRow) {
        // Deterministic Update: Overwrite ONLY columns 1 to 16.
        // Columns 17+ (Q onward) with manual notes/sales stage are PRESERVED intact.
        sheet.getRange(targetRow, 1, 1, STANDARD_HEADERS.length).setValues([rowValues]);
        if (!seenInCurrentSync[bid]) {
          updatedCount++;
        }
      } else {
        // Append new row at bottom with exactly 16 columns
        var newRowIdx = sheet.getLastRow() + 1;
        sheet.getRange(newRowIdx, 1, 1, STANDARD_HEADERS.length).setValues([rowValues]);
        idToRowMap[bid] = newRowIdx;
        appendedCount++;
      }
      seenInCurrentSync[bid] = true;
    }

    return jsonResponse({
      success: true,
      status: "connected",
      message: "Sync completed successfully",
      sync_run_id: data.sync_run_id || null,
      updated_count: updatedCount,
      appended_count: appendedCount,
      total_processed: records.length,
      current_sheet_rows: sheet.getLastRow(),
      synced_at: syncTimestamp
    });

  } catch (err) {
    Logger.log("doPost Error: " + err.toString());
    return jsonResponse({
      success: false,
      status: "error",
      error: "Apps Script exception: " + err.toString()
    });
  }
}

/**
 * Health check endpoint for testing deployment status in a browser.
 * Never outputs the secret.
 */
function doGet(e) {
  var hasSecret = Boolean(getWebhookSecret());
  return jsonResponse({
    status: "ok",
    service: "SparkXFlow Google Sheets Synchronization Bridge",
    target_spreadsheet_id: TARGET_SPREADSHEET_ID,
    target_sheet_gid: TARGET_SHEET_GID,
    secret_configured: hasSecret,
    timestamp: new Date().toISOString()
  });
}

/**
 * Manual test function: run directly from the Apps Script editor
 * to verify permissions and row insertion safely.
 */
function testSyncManually() {
  var secret = getWebhookSecret();
  if (!secret) {
    Logger.log("⚠️ Cannot run testSyncManually: Please run setupWebhookSecret('your-secret') first.");
    return;
  }

  var mockPayload = {
    postData: {
      contents: JSON.stringify({
        secret: secret,
        sync_run_id: "test-run-" + new Date().getTime(),
        sheet_id: TARGET_SPREADSHEET_ID,
        sheet_gid: TARGET_SHEET_GID,
        synced_at: new Date().toISOString(),
        records: [
          {
            business_id: "test-manual-lead-001",
            name: "SparkXFlow Verification Test Lead",
            website: "https://example.com/test",
            domain: "example.com",
            industry: "Logistics",
            sub_industry: "Freight Logistics",
            city: "Bengaluru",
            country: "India",
            top_recommended_service: "Website Optimization",
            opportunity_score: 92,
            quality_score: 88,
            contacts: "Test Rep (Sales): test@example.com",
            discovery_source: "manual_verification",
            discovered_at: new Date().toISOString()
          }
        ]
      })
    }
  };

  var response = doPost(mockPayload);
  Logger.log("Test Output: " + response.getContent());
}

/**
 * Formats a clean JSON response via ContentService.
 */
function jsonResponse(obj) {
  var output = ContentService.createTextOutput(JSON.stringify(obj, null, 2));
  output.setMimeType(ContentService.MimeType.JSON);
  return output;
}
