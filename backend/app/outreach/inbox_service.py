"""Inbox Synchronization and Reply Classification for SparkXFlow Engine D.
Classifies inbound responses, suggests context-aware replies for human review,
and automatically enforces suppression on opt-out/unsubscribe requests.
"""
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InboxMessage, OutreachMessage, SuppressionEntry, FollowUpTask, now, uid

class ReplyClassifier:
    @staticmethod
    def classify(text: str) -> str:
        t = text.lower()
        if any(w in t for w in ['unsubscribe', 'remove me', 'stop emailing', 'opt out', 'take me off']):
            return 'unsubscribe'
        if any(w in t for w in ['calendar', 'meet', 'call next week', 'zoom', 'schedule', 'available on', 'tuesday', 'thursday']):
            return 'meeting_interest'
        if any(w in t for w in ['interested', 'pricing', 'how much', 'case study', 'portfolio', 'send more details', 'tell me more']):
            return 'more_info'
        if any(w in t for w in ['sounds good', 'let\'s talk', 'sure', 'connect with', 'great idea']):
            return 'positive'
        if any(w in t for w in ['not interested', 'no thanks', 'do not need', 'already have', 'wrong person', 'no budget']):
            return 'negative'
        return 'neutral'

    @staticmethod
    def suggest_reply(classification: str, sender_name: str = '') -> str:
        salutation = f"Hi {sender_name.split()[0]}," if sender_name else "Hi,"
        if classification == 'meeting_interest':
            return (
                f"{salutation}\n\nThank you for getting back to me! I would be delighted to connect. "
                "Would Tuesday or Thursday afternoon work for a quick 15-minute introductory video call? "
                "Alternatively, feel free to pick a time directly on my calendar: https://sparkxflow.agency/calendar\n\nBest regards,\nAlex Rivera"
            )
        elif classification == 'more_info':
            return (
                f"{salutation}\n\nAppreciate your interest! I've attached a one-page overview of our agency methodology "
                "along with relevant case studies in your industry. Would you like to schedule a brief walk-through next week?\n\nBest regards,\nAlex Rivera"
            )
        elif classification == 'positive':
            return (
                f"{salutation}\n\nFantastic to hear! What does your calendar look like early next week to discuss this further?\n\nBest regards,\nAlex Rivera"
            )
        elif classification == 'unsubscribe':
            return (
                f"{salutation}\n\nYou have been removed from our contact list and will receive no further communications from SparkXFlow. "
                "Wishing you the best with your business.\n\nBest regards,\nAlex Rivera"
            )
        return f"{salutation}\n\nThank you for your message. Let me know if you would like any specific information regarding our agency services.\n\nBest regards,\nAlex Rivera"

class InboxService:
    def __init__(self, session: Session):
        self.session = session

    def record_incoming_message(self,
                                sender_email: str,
                                recipient_email: str,
                                subject: str,
                                body: str,
                                outreach_message_id: Optional[str] = None) -> InboxMessage:
        classification = ReplyClassifier.classify(body)
        suggested = ReplyClassifier.suggest_reply(classification)

        business_id = None
        contact_id = None
        if outreach_message_id:
            parent = self.session.get(OutreachMessage, outreach_message_id)
            if parent:
                business_id = parent.business_id
                contact_id = parent.contact_id

        msg = InboxMessage(
            outreach_message_id=outreach_message_id,
            business_id=business_id,
            contact_id=contact_id,
            direction='inbound',
            sender=sender_email.strip().lower(),
            recipient=recipient_email.strip().lower(),
            subject=subject.strip(),
            body=body.strip(),
            classification=classification,
            suggested_reply=suggested,
            received_at=now(),
            created_at=now()
        )
        self.session.add(msg)

        # Automatic safety: if reply is unsubscribe, add to suppression list
        if classification == 'unsubscribe':
            existing_sup = self.session.scalars(
                select(SuppressionEntry).where(SuppressionEntry.email == sender_email.lower())
            ).first()
            if not existing_sup:
                self.session.add(SuppressionEntry(
                    email=sender_email.lower(),
                    reason='Recipient requested unsubscribe / opt-out',
                    added_at=now()
                ))

            # Cancel any pending follow-ups for this contact/business
            if business_id:
                pending_tasks = self.session.scalars(
                    select(FollowUpTask).where(
                        FollowUpTask.business_id == business_id,
                        FollowUpTask.status.in_(['scheduled', 'pending_approval'])
                    )
                ).all()
                for task in pending_tasks:
                    task.status = 'cancelled'
                    task.cancellation_reason = 'Cancelled due to unsubscribe request'

        self.session.commit()
        return msg

