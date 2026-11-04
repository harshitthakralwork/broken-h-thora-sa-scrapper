"""Google Sheets Synchronization Service for SparkXFlow.
Supports bidirectional sync using lightweight Google Apps Script Webhook bridge.
Ensures SQLite remains the single source of truth, preserves existing rows,
authenticates via dedicated SHEETS_WEBHOOK_SECRET, and prevents row duplication.
"""
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Business, BusinessProfile, LeadQualification, Contact, SystemIntegration, now

logger = logging.getLogger('sparkxflow.integrations.sheets')

TARGET_SPREADSHEET_ID = "1jSxjVQUi-RgQzTmOx42nla3JwguIhIkbqNJXlkxPPgk"
TARGET_SHEET_GID = 0

class GoogleSheetsSyncService:
    def __init__(self, session: Session):
        self.session = session

    def get_webhook_secret(self, cfg: Optional[Dict[str, Any]] = None) -> str:
        """Resolve dedicated webhook secret from config or environment variable.
        Never reuses ADMIN_TOKEN."""
        if cfg and cfg.get('webhook_secret'):
            return cfg['webhook_secret'].strip()
        env_secret = os.environ.get('SHEETS_WEBHOOK_SECRET', '').strip()
        return env_secret

    def get_or_create_config(self) -> SystemIntegration:
        integration = self.session.scalars(
            select(SystemIntegration).where(SystemIntegration.service_name == 'google_sheets')
        ).first()
        if not integration:
            default_secret = os.environ.get('SHEETS_WEBHOOK_SECRET', '')
            integration = SystemIntegration(
                service_name='google_sheets',
                is_enabled=False,
                status='unconfigured',
                config_json=json.dumps({
                    'webhook_url': '',
                    'sheet_id': TARGET_SPREADSHEET_ID,
                    'sheet_gid': TARGET_SHEET_GID,
                    'webhook_secret': default_secret,
                    'mode': 'apps_script_bridge',
                    'auto_sync_interval_mins': 60
                }),
                created_at=now()
            )
            self.session.add(integration)
            self.session.commit()
        return integration

    def update_config(self,
                      webhook_url: str = '',
                      sheet_id: str = '',
                      webhook_secret: Optional[str] = None,
                      is_enabled: bool = True) -> SystemIntegration:
        integration = self.get_or_create_config()
        cfg = json.loads(integration.config_json or '{}')
        if webhook_url is not None:
            cfg['webhook_url'] = webhook_url.strip()
        if sheet_id is not None and sheet_id.strip():
            clean_sheet_id = sheet_id.strip()
            if clean_sheet_id != TARGET_SPREADSHEET_ID:
                raise ValueError(f"Unauthorized spreadsheet ID: '{clean_sheet_id}'. Target must match configured '{TARGET_SPREADSHEET_ID}'.")
            cfg['sheet_id'] = clean_sheet_id
        elif not cfg.get('sheet_id'):
            cfg['sheet_id'] = TARGET_SPREADSHEET_ID
        if webhook_secret is not None:
            cfg['webhook_secret'] = webhook_secret.strip()

        integration.config_json = json.dumps(cfg)
        integration.is_enabled = is_enabled
        clean_url = cfg.get('webhook_url', '')
        integration.status = 'configured' if clean_url else 'unconfigured'
        integration.error_message = ''
        self.session.commit()
        return integration

    def get_safe_config(self) -> Dict[str, Any]:
        """Return configuration with secret redacted."""
        integration = self.get_or_create_config()
        cfg = json.loads(integration.config_json or '{}')
        has_secret = bool(self.get_webhook_secret(cfg))
        safe_cfg = {
            'webhook_url': cfg.get('webhook_url', ''),
            'sheet_id': cfg.get('sheet_id', TARGET_SPREADSHEET_ID),
            'sheet_gid': cfg.get('sheet_gid', TARGET_SHEET_GID),
            'has_secret': has_secret,
            'webhook_secret_masked': '••••••••' if has_secret else '',
            'mode': cfg.get('mode', 'apps_script_bridge'),
            'auto_sync_interval_mins': cfg.get('auto_sync_interval_mins', 60)
        }
        return safe_cfg

    def prepare_export_payload(self) -> List[Dict[str, Any]]:
        rows = []
        businesses = self.session.scalars(
            select(Business).order_by(Business.created_at.desc())
        ).all()

        for b in businesses:
            profile = self.session.get(BusinessProfile, b.id)
            qual = self.session.scalars(
                select(LeadQualification).where(LeadQualification.business_id == b.id).order_by(LeadQualification.created_at.desc())
            ).first()
            contacts = self.session.scalars(
                select(Contact).where(Contact.business_id == b.id)
            ).all()

            contact_summary = "; ".join([f"{c.full_name} ({c.job_title}): {c.email or 'N/A'}" for c in contacts]) if contacts else "None"

            top_service = "Website Development"
            top_score = 0
            if qual and qual.service_scores_json:
                try:
                    scores = json.loads(qual.service_scores_json)
                    if isinstance(scores, list) and scores:
                        top = max(scores, key=lambda x: x.get('score', 0))
                        top_service = top.get('service', 'Website Development')
                        top_score = top.get('score', 0)
                except Exception:
                    pass

            rows.append({
                'business_id': b.id,
                'name': b.name,
                'website': b.website or '',
                'domain': b.domain or '',
                'industry': b.industry or '',
                'sub_industry': profile.sub_industry if profile else '',
                'country': profile.country if profile else '',
                'city': profile.city if profile else b.location,
                'top_recommended_service': top_service,
                'opportunity_score': top_score,
                'quality_score': qual.business_quality_score if qual else 0,
                'contacts': contact_summary,
                'discovery_source': b.source,
                'discovered_at': b.created_at.isoformat()
            })
        return rows

    def sync_to_sheets(self) -> Dict[str, Any]:
        """Synchronize discovered leads to Google Sheets via Apps Script Webhook.
        Follows redirects (302) required by Google Apps Script web apps."""
        integration = self.get_or_create_config()
        cfg = json.loads(integration.config_json or '{}')
        webhook_url = (cfg.get('webhook_url') or '').strip()
        sheet_id = cfg.get('sheet_id') or TARGET_SPREADSHEET_ID
        secret = self.get_webhook_secret(cfg)

        payload = self.prepare_export_payload()

        if not webhook_url:
            integration.status = 'unconfigured'
            integration.error_message = 'Google Apps Script Webhook URL is not configured'
            self.session.commit()
            return {
                'success': False,
                'status': 'unconfigured',
                'records_prepared': len(payload),
                'notice': 'Google Apps Script Webhook URL is not configured. Setup instructions: In Google Sheets, click Extensions > Apps Script, paste the SparkXFlow sync handler, Deploy as Web App with access "Anyone", and paste the Web App URL in Google Sheets Sync.'
            }

        if not secret:
            integration.status = 'unconfigured'
            integration.error_message = 'Google Sheets Webhook Secret (SHEETS_WEBHOOK_SECRET) is not configured'
            self.session.commit()
            return {
                'success': False,
                'status': 'unconfigured',
                'records_prepared': len(payload),
                'notice': 'Google Sheets Webhook Secret is not configured. Set SHEETS_WEBHOOK_SECRET in .env or configure in Google Sheets Sync settings.'
            }

        sync_run_id = f"sync-{uuid.uuid4().hex[:10]}"
        request_body = {
            'secret': secret,
            'sync_run_id': sync_run_id,
            'sheet_id': TARGET_SPREADSHEET_ID,
            'sheet_gid': TARGET_SHEET_GID,
            'records': payload,
            'synced_at': now().isoformat(),
            'system': 'SparkXFlow Lead Intelligence Engine'
        }

        max_retries = 2
        last_exception = None
        attempt = 0
        for attempt in range(max_retries + 1):
            try:
                # follow_redirects=True is mandatory because Google Apps Script web apps return 302 redirects
                with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                    res = client.post(
                        webhook_url,
                        json=request_body,
                        headers={
                            'X-Webhook-Secret': secret,
                            'Content-Type': 'application/json'
                        }
                    )
                    if res.status_code in [200, 201]:
                        try:
                            resp_json = res.json()
                        except Exception:
                            resp_json = {'success': False, 'error': f'Webhook returned non-JSON response: {res.text[:120]}'}

                        # Google Apps Script ContentService returns HTTP 200 even for authorization/validation failures.
                        # We must strictly verify that resp_json explicitly confirms success == True.
                        if not (isinstance(resp_json, dict) and resp_json.get('success') is True):
                            err_msg = resp_json.get('error', 'Apps Script did not confirm success') if isinstance(resp_json, dict) else 'Apps Script returned non-dictionary response'
                            integration.status = 'error'
                            integration.error_message = err_msg
                            self.session.commit()
                            return {
                                'success': False,
                                'status': resp_json.get('status', 'error') if isinstance(resp_json, dict) else 'error',
                                'error': err_msg,
                                'records_prepared': len(payload),
                                'apps_script_response': resp_json,
                                'attempts': attempt + 1
                            }

                        integration.last_synced_at = now()
                        integration.status = 'connected'
                        integration.error_message = ''
                        self.session.commit()
                        return {
                            'success': True,
                            'status': 'connected',
                            'sync_run_id': sync_run_id,
                            'records_synced': len(payload),
                            'apps_script_response': resp_json,
                            'attempts': attempt + 1
                        }
                    elif res.status_code in (401, 403):
                        err_msg = f"Apps Script authentication failed (HTTP {res.status_code}): Invalid webhook secret or permissions"
                        integration.status = 'error'
                        integration.error_message = err_msg
                        self.session.commit()
                        return {'success': False, 'status': 'unauthorized', 'error': err_msg, 'attempts': attempt + 1}
                    elif res.status_code in (502, 503, 504) and attempt < max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    else:
                        raise RuntimeError(f"Webhook responded with HTTP {res.status_code}: {res.text[:120]}")
            except (httpx.TimeoutException, httpx.NetworkError, RuntimeError) as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_exception = e
                break

        logger.exception("Failed to sync to Google Sheets webhook after %d attempts", attempt + 1)
        integration.status = 'error'
        integration.error_message = str(last_exception)
        self.session.commit()
        return {
            'success': False,
            'status': 'error',
            'error': str(last_exception),
            'records_prepared': len(payload),
            'attempts': attempt + 1
        }

    def import_from_sheets(self, incoming_data: Dict[str, Any]) -> Dict[str, Any]:
        """Safely import edits from Google Sheets back into SparkXFlow database.
        Validates secret using constant-time comparison, validates fields, and prevents overwriting newer data."""
        integration = self.get_or_create_config()
        cfg = json.loads(integration.config_json or '{}')
        expected_secret = self.get_webhook_secret(cfg)

        if not expected_secret or not expected_secret.strip():
            return {'success': False, 'status': 'unauthorized', 'error': 'Webhook secret is not configured on server'}

        provided_secret = (incoming_data.get('secret') or '').strip()
        if not provided_secret or not secrets.compare_digest(provided_secret, expected_secret.strip()):
            return {'success': False, 'status': 'unauthorized', 'error': 'Invalid webhook secret'}

        records = incoming_data.get('records') or []
        if not isinstance(records, list):
            return {'success': False, 'status': 'invalid_payload', 'error': 'Expected "records" list'}

        updated_count = 0
        skipped_count = 0
        errors = []

        for row in records:
            if not isinstance(row, dict):
                continue
            bid = (row.get('business_id') or '').strip()
            if not bid:
                skipped_count += 1
                continue

            business = self.session.get(Business, bid)
            if not business:
                skipped_count += 1
                continue

            profile = self.session.get(BusinessProfile, bid)
            # Timestamp conflict check: if DB record was researched or updated after spreadsheet sync time, do not overwrite
            sheet_synced_at = row.get('last_synced_at')
            if sheet_synced_at and profile and profile.updated_at:
                try:
                    sync_dt = datetime.fromisoformat(sheet_synced_at.replace('Z', '+00:00'))
                    if profile.updated_at > sync_dt:
                        # Database is newer, skip to prevent overwriting newer insights
                        skipped_count += 1
                        continue
                except Exception:
                    pass

            # Update safe editable fields
            if row.get('industry') and isinstance(row['industry'], str):
                business.industry = row['industry'].strip()
            if row.get('city') and isinstance(row['city'], str) and profile:
                profile.city = row['city'].strip()
            if row.get('sub_industry') and isinstance(row['sub_industry'], str) and profile:
                profile.sub_industry = row['sub_industry'].strip()

            updated_count += 1

        self.session.commit()
        return {
            'success': True,
            'updated_count': updated_count,
            'skipped_count': skipped_count,
            'errors': errors
        }
