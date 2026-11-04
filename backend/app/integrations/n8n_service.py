"""n8n Workflow Automation Bridge for SparkXFlow.
Enforces event-driven webhook dispatches to n8n pipelines with cryptographic idempotency keys,
transparent unconfigured statuses, and zero bypassing of backend human approval gates.
"""
import hashlib
import json
import logging
import uuid
from typing import Dict, Any, Optional, List
import httpx

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SystemIntegration, now

logger = logging.getLogger('sparkxflow.integrations.n8n')

SUPPORTED_N8N_EVENTS = [
    'lead.discovered',
    'lead.qualified',
    'approval.required',
    'email.approved',
    'followup.draft',
    'reply.received'
]

class N8nAutomationService:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_config(self) -> SystemIntegration:
        integration = self.session.scalars(
            select(SystemIntegration).where(SystemIntegration.service_name == 'n8n_automation')
        ).first()
        if not integration:
            integration = SystemIntegration(
                service_name='n8n_automation',
                is_enabled=False,
                status='unconfigured',
                config_json=json.dumps({
                    'webhook_url': '',
                    'events': SUPPORTED_N8N_EVENTS
                }),
                created_at=now()
            )
            self.session.add(integration)
            self.session.commit()
        return integration

    def update_config(self, webhook_url: str = '', is_enabled: bool = True, events: Optional[List[str]] = None) -> SystemIntegration:
        integration = self.get_or_create_config()
        cfg = json.loads(integration.config_json or '{}')
        if webhook_url is not None:
            cfg['webhook_url'] = webhook_url.strip()
        if events is not None:
            cfg['events'] = [e for e in events if e in SUPPORTED_N8N_EVENTS]
        integration.config_json = json.dumps(cfg)
        integration.is_enabled = is_enabled
        clean_url = cfg.get('webhook_url', '')
        integration.status = 'configured' if clean_url else 'unconfigured'
        integration.error_message = ''
        self.session.commit()
        return integration

    def dispatch_event(self, event_name: str, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Send event to n8n Webhook node with idempotency guarantees."""
        integration = self.get_or_create_config()
        if not integration.is_enabled:
            return {'dispatched': False, 'status': 'disabled', 'reason': 'n8n integration is disabled'}

        cfg = json.loads(integration.config_json or '{}')
        webhook_url = (cfg.get('webhook_url') or '').strip()
        if not webhook_url:
            integration.status = 'unconfigured'
            self.session.commit()
            return {
                'dispatched': False,
                'status': 'unconfigured',
                'reason': 'n8n Webhook URL is not configured. Setup instructions: In n8n, add a Webhook Trigger node (POST) and paste the webhook URL in SparkXFlow Integrations.'
            }

        allowed_events = cfg.get('events', SUPPORTED_N8N_EVENTS)
        if event_name not in allowed_events:
            return {'dispatched': False, 'status': 'filtered', 'reason': f"Event {event_name} not in subscribed events list"}

        delivery_id = str(uuid.uuid4())
        if not idempotency_key:
            hash_src = f"{event_name}:{json.dumps(payload, sort_keys=True)}".encode('utf-8')
            idempotency_key = hashlib.sha256(hash_src).hexdigest()[:32]

        body = {
            'event': event_name,
            'delivery_id': delivery_id,
            'idempotency_key': idempotency_key,
            'timestamp': now().isoformat(),
            'data': payload
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.post(
                    webhook_url,
                    json=body,
                    headers={
                        'X-SparkXFlow-Event': event_name,
                        'X-SparkXFlow-Delivery-Id': delivery_id,
                        'X-SparkXFlow-Idempotency-Key': idempotency_key,
                        'Content-Type': 'application/json'
                    }
                )
                if res.status_code in [200, 201, 202, 204]:
                    integration.last_synced_at = now()
                    integration.status = 'connected'
                    integration.error_message = ''
                    self.session.commit()
                    return {'dispatched': True, 'status': 'connected', 'delivery_id': delivery_id, 'http_status': res.status_code}
                else:
                    err = f"n8n webhook returned HTTP {res.status_code}: {res.text[:100]}"
                    integration.status = 'error'
                    integration.error_message = err
                    self.session.commit()
                    return {'dispatched': False, 'status': 'error', 'error': err}
        except Exception as e:
            err = f"Failed to dispatch to n8n: {str(e)}"
            logger.warning(err)
            integration.status = 'error'
            integration.error_message = err
            self.session.commit()
            return {'dispatched': False, 'status': 'error', 'error': err}

    def test_connection(self) -> Dict[str, Any]:
        """Dispatch a safe ping / test event to verify n8n webhook connectivity."""
        return self.dispatch_event(
            event_name='test.ping',
            payload={'message': 'SparkXFlow n8n integration ping', 'timestamp': now().isoformat()},
            idempotency_key=f"test-ping-{now().strftime('%Y%m%d%H%M%S')}"
        )
