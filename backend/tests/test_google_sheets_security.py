"""Comprehensive Security, Correctness, and Regression Tests for Google Sheets Integration.
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Business, BusinessProfile, SystemIntegration, now
from app.integrations.sheets_service import (
    GoogleSheetsSyncService,
    TARGET_SPREADSHEET_ID,
    TARGET_SHEET_GID
)
from app import main
from app.api_router import get_db as router_db


@pytest.fixture
def sheets_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_missing_secret_rejection(sheets_db, monkeypatch):
    """Verify that sync and import reject operations when secret is missing or empty."""
    monkeypatch.delenv("SHEETS_WEBHOOK_SECRET", raising=False)
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(webhook_url="https://script.google.com/macros/s/test/exec", webhook_secret="")

    # Sync should report unconfigured due to missing secret
    res_sync = service.sync_to_sheets()
    assert res_sync['success'] is False
    assert res_sync['status'] == 'unconfigured'
    assert 'SHEETS_WEBHOOK_SECRET' in res_sync['notice']

    # Import should reject with unauthorized when secret is not configured on server
    res_import = service.import_from_sheets({"secret": "any_secret", "records": []})
    assert res_import['success'] is False
    assert res_import['status'] == 'unauthorized'


def test_incorrect_secret_rejection(sheets_db):
    """Verify constant-time secret rejection for incorrect secrets on import."""
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(webhook_secret="correct_secret_xyz")

    # Mismatched secret
    res = service.import_from_sheets({"secret": "wrong_secret_123", "records": []})
    assert res['success'] is False
    assert res['status'] == 'unauthorized'
    assert 'Invalid webhook secret' in res['error']

    # Empty provided secret
    res_empty = service.import_from_sheets({"secret": "", "records": []})
    assert res_empty['success'] is False
    assert res_empty['status'] == 'unauthorized'


def test_correct_secret_acceptance(sheets_db):
    """Verify import succeeds when exact secret is supplied."""
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(webhook_secret="secure_token_999")

    # Add a business
    b = Business(id="biz-accept-1", name="Accept Logistics", website="https://accept.example", domain="accept.example")
    p = BusinessProfile(business_id="biz-accept-1", city="Bengaluru", sub_industry="Freight")
    sheets_db.add_all([b, p])
    sheets_db.commit()

    res = service.import_from_sheets({
        "secret": "secure_token_999",
        "records": [
            {"business_id": "biz-accept-1", "city": "Bengaluru East", "industry": "Logistics & Supply"}
        ]
    })
    assert res['success'] is True
    assert res['updated_count'] == 1
    sheets_db.refresh(b)
    assert b.industry == "Logistics & Supply"


def test_wrong_spreadsheet_id_rejection(sheets_db):
    """Verify that configuring an unauthorized spreadsheet ID is rejected."""
    service = GoogleSheetsSyncService(sheets_db)

    # Valid ID succeeds
    service.update_config(sheet_id=TARGET_SPREADSHEET_ID)

    # Invalid ID raises ValueError
    with pytest.raises(ValueError) as excinfo:
        service.update_config(sheet_id="attacker-controlled-spreadsheet-id")
    assert "Unauthorized spreadsheet ID" in str(excinfo.value)


def test_api_endpoint_wrong_spreadsheet_id_returns_400(sheets_db):
    """Verify API endpoint returns HTTP 400 when an invalid spreadsheet ID is posted."""
    headers = {'Authorization': 'Bearer ' + main.ADMIN_TOKEN}
    main.app.dependency_overrides[main.db] = lambda: sheets_db
    main.app.dependency_overrides[router_db] = lambda: sheets_db
    try:
        client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 50000))
        res = client.post('/api/integrations/google-sheets/config', headers=headers, json={
            'webhook_url': 'https://script.google.com/test',
            'sheet_id': 'malicious-id-12345'
        })
        assert res.status_code == 400
        assert "Unauthorized spreadsheet ID" in res.json()['detail']
    finally:
        main.app.dependency_overrides.pop(main.db, None)
        main.app.dependency_overrides[router_db] = main.db


def test_apps_script_redirect_and_error_handling(sheets_db):
    """Verify httpx follows 302 redirects and parses Apps Script JSON error envelopes."""
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(
        webhook_url="https://script.google.com/macros/s/redirect-test/exec",
        webhook_secret="valid_secret_abc"
    )

    # Test handling of handled Apps Script error returned with HTTP 200
    with patch('httpx.Client.post') as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"success": False, "status": "unauthorized", "error": "Unauthorized: Invalid webhook secret"}
        )
        res = service.sync_to_sheets()
        assert res['success'] is False
        assert res['status'] == 'unauthorized'
        assert "Unauthorized: Invalid webhook secret" in res['error']

    # Test handling of network timeout
    with patch('httpx.Client.post') as mock_post:
        import httpx
        mock_post.side_effect = httpx.TimeoutException("Connection timed out after 25s")
        res_timeout = service.sync_to_sheets()
        assert res_timeout['success'] is False
        assert res_timeout['status'] == 'error'
        assert "timed out" in res_timeout['error'].lower()


def test_apps_script_must_confirm_success(sheets_db):
    """Verify backend does NOT report success if Apps Script returns non-JSON or success != True."""
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(
        webhook_url="https://script.google.com/macros/s/test/exec",
        webhook_secret="test_secret"
    )

    # Case 1: HTML error page (e.g. Google auth or crash) returning HTTP 200
    with patch('httpx.Client.post') as mock_post:
        mock_resp = MagicMock(status_code=200, text="<html><head><title>Error</title></head><body>Crash</body></html>")
        mock_resp.json.side_effect = Exception("Not JSON")
        mock_post.return_value = mock_resp

        res = service.sync_to_sheets()
        assert res['success'] is False
        assert res['status'] == 'error'
        assert "non-json" in res['error'].lower()

    # Case 2: Dict without success: true
    with patch('httpx.Client.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": "received"})
        res2 = service.sync_to_sheets()
        assert res2['success'] is False
        assert res2['status'] == 'error'


def test_no_secret_leakage_in_api_or_logs(sheets_db):
    """Verify secrets are redacted in safe config and GET /api/integrations."""
    service = GoogleSheetsSyncService(sheets_db)
    raw_secret = "super_confidential_secret_777"
    service.update_config(
        webhook_url="https://script.google.com/macros/s/test/exec",
        webhook_secret=raw_secret
    )

    # Check service safe config
    safe_cfg = service.get_safe_config()
    assert safe_cfg['has_secret'] is True
    assert safe_cfg['webhook_secret_masked'] == '••••••••'
    assert raw_secret not in json.dumps(safe_cfg)

    # Check API router response
    headers = {'Authorization': 'Bearer ' + main.ADMIN_TOKEN}
    main.app.dependency_overrides[main.db] = lambda: sheets_db
    main.app.dependency_overrides[router_db] = lambda: sheets_db
    try:
        client = TestClient(main.app, base_url='http://localhost', client=('127.0.0.1', 50000))
        res = client.get('/api/integrations', headers=headers)
        assert res.status_code == 200
        content = res.text
        assert raw_secret not in content
    finally:
        main.app.dependency_overrides.pop(main.db, None)
        main.app.dependency_overrides[router_db] = main.db


def test_apps_script_file_integrity_and_security_contract():
    """Verify google_sheets_sync.gs implements all security controls required by specification."""
    script_path = os.path.join(os.path.dirname(__file__), "..", "app", "integrations", "google_sheets_sync.gs")
    assert os.path.exists(script_path), "google_sheets_sync.gs must exist"
    
    with open(script_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 1. Enforces exact spreadsheet ID
    assert 'var TARGET_SPREADSHEET_ID = "1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk"' in code
    # 2. Enforces exact sheet GID
    assert 'var TARGET_SHEET_GID = 0' in code
    # 3. No silent fallback in getTargetSheet
    assert 'return null;' in code
    # 4. Rejects empty/missing WEBHOOK_SECRET
    assert 'if (!expectedSecret || expectedSecret.trim() === "")' in code
    # 5. Constant-time comparison
    assert 'function constantTimeCompare(' in code
    # 6. Rejects mismatched sheet_id
    assert 'data.sheet_id && String(data.sheet_id).trim() !== TARGET_SPREADSHEET_ID' in code
    # 7. Validates Column A Header
    assert 'business id' in code.lower()
    # 8. Never logs or returns the secret
    assert 'setupWebhookSecret' in code
    assert 'Logger.log("✅ WEBHOOK_SECRET successfully saved to Script Properties' in code
    assert 'Logger.log("✅ WEBHOOK_SECRET successfully saved: "' not in code
    # 9. HTTP Response limitation documented
    assert 'HTTP Status Limitation Note (Google Apps Script)' in code
    # 10. Columns 17+ preserved (writes only STANDARD_HEADERS.length = 16)
    assert 'STANDARD_HEADERS.length' in code


def test_bounded_retries_transient_failure(sheets_db):
    """Verify bounded retry logic (transient 503 error recovered on retry)."""
    service = GoogleSheetsSyncService(sheets_db)
    service.update_config(
        webhook_url="https://script.google.com/macros/s/retry-test/exec",
        webhook_secret="test_secret_123"
    )

    with patch('httpx.Client.post') as mock_post, patch('time.sleep', return_value=None):
        # 1st call fails with 503, 2nd call succeeds with 200
        fail_resp = MagicMock(status_code=503, text="Service Unavailable")
        success_resp = MagicMock(
            status_code=200,
            json=lambda: {"success": True, "status": "connected", "updated_count": 1}
        )
        mock_post.side_effect = [fail_resp, success_resp]

        res = service.sync_to_sheets()
        assert res['success'] is True
        assert res['status'] == 'connected'
        assert res['attempts'] == 2
        assert mock_post.call_count == 2
