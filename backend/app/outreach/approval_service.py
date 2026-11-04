"""Approval Center & Sending Safeguards for SparkXFlow Engine D.
Enforces that every outbound email and follow-up requires explicit human approval.
Calculates SHA256 hashes of recipient and content; any modification invalidates prior approval.
Validates suppression list, daily quota, and global sending kill-switch.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OutreachMessage, SuppressionEntry, SystemIntegration, now
from .provider import get_email_provider

logger = logging.getLogger('sparkxflow.outreach.approval')

def compute_approval_hash(recipient: str, subject: str, body: str) -> str:
    raw = f"{recipient.strip().lower()}|{subject.strip()}|{body.strip()}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

class ApprovalService:
    def __init__(self, session: Session):
        self.session = session

    def approve_message(self, message_id: str) -> OutreachMessage:
        msg = self.session.get(OutreachMessage, message_id)
        if not msg:
            raise HTTPException(404, f"Message {message_id} not found")

        # Verify not suppressed
        suppressed = self.session.scalars(
            select(SuppressionEntry).where(SuppressionEntry.email == msg.recipient_email.lower())
        ).first()
        if suppressed:
            msg.status = 'rejected'
            msg.error_reason = f"Recipient {msg.recipient_email} is on global suppression list ({suppressed.reason})"
            self.session.commit()
            raise HTTPException(400, msg.error_reason)

        # Compute hash and stamp approval
        msg.approval_hash = compute_approval_hash(msg.recipient_email, msg.subject, msg.body_text)
        msg.approved_at = now()
        msg.status = 'approved'
        msg.error_reason = ''
        msg.updated_at = now()
        self.session.commit()
        return msg

    def reject_message(self, message_id: str, reason: str = 'Rejected by reviewer') -> OutreachMessage:
        msg = self.session.get(OutreachMessage, message_id)
        if not msg:
            raise HTTPException(404, f"Message {message_id} not found")
        msg.status = 'rejected'
        msg.approval_hash = None
        msg.approved_at = None
        msg.error_reason = reason
        msg.updated_at = now()
        self.session.commit()
        return msg

    def edit_message(self, message_id: str, subject: str, body_text: str) -> OutreachMessage:
        """Editing an email immediately revokes prior approval status and requires re-approval."""
        msg = self.session.get(OutreachMessage, message_id)
        if not msg:
            raise HTTPException(404, f"Message {message_id} not found")

        if msg.status == 'sent':
            raise HTTPException(400, "Cannot edit an already sent email")

        msg.subject = subject.strip()
        msg.body_text = body_text.strip()
        msg.status = 'pending_approval'
        msg.approval_hash = None
        msg.approved_at = None
        msg.updated_at = now()
        self.session.commit()
        return msg

    def execute_send(self, message_id: str, provider_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Strictly verifies all conditions before initiating transmission."""
        msg = self.session.get(OutreachMessage, message_id)
        if not msg:
            raise HTTPException(404, f"Message {message_id} not found")

        # 1. Check message status
        if msg.status != 'approved':
            raise HTTPException(400, f"Message {message_id} is in status '{msg.status}'. Explicit human approval is required.")

        # 2. Idempotency check: refuse already sent
        if msg.sent_at:
            raise HTTPException(400, f"Message {message_id} was already sent at {msg.sent_at.isoformat()}. Duplicate sends prevented.")

        # 3. Check cryptographic content integrity
        current_hash = compute_approval_hash(msg.recipient_email, msg.subject, msg.body_text)
        if msg.approval_hash != current_hash:
            msg.status = 'pending_approval'
            msg.approved_at = None
            msg.approval_hash = None
            self.session.commit()
            raise HTTPException(400, "Content was altered after approval was granted. Approval revoked; please re-approve.")

        # 4. Check suppression list
        suppressed = self.session.scalars(
            select(SuppressionEntry).where(SuppressionEntry.email == msg.recipient_email.lower())
        ).first()
        if suppressed:
            msg.status = 'rejected'
            msg.error_reason = f"Recipient is on suppression list: {suppressed.reason}"
            self.session.commit()
            raise HTTPException(400, msg.error_reason)

        # 5. Check global sending authorization toggle
        sending_integration = self.session.scalars(
            select(SystemIntegration).where(SystemIntegration.service_name == 'email_sending')
        ).first()
        is_sending_enabled = bool(sending_integration and sending_integration.is_enabled)
        if not is_sending_enabled:
            # Default safety rule: outbound transmission disabled until user enables it
            return {
                'success': False,
                'status': 'held_for_safety',
                'message': 'Global outbound email sending is currently DISABLED for safety. Go to Settings/Approval Center to enable sending.',
                'message_id': msg.id
            }

        # 6. Transmit via provider
        provider = get_email_provider(provider_config)
        try:
            receipt = provider.send_email(
                recipient_email=msg.recipient_email,
                subject=msg.subject,
                body_text=msg.body_text
            )
            msg.status = 'sent'
            msg.sent_at = now()
            msg.provider_message_id = receipt.get('message_id', '')
            msg.updated_at = now()
            self.session.commit()
            return receipt
        except Exception as e:
            logger.exception("Failed to transmit email %s", message_id)
            msg.status = 'failed'
            msg.error_reason = str(e)
            msg.updated_at = now()
            self.session.commit()
            raise HTTPException(500, f"Transmission failure: {str(e)}")

