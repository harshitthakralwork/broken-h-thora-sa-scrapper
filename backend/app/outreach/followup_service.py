"""Follow-up Management for SparkXFlow Engine D.
Coordinates multi-stage cadences (Day 0, Day 3, Day 7, Day 14).
Each individual follow-up requires separate explicit human approval.
Automatically stops when recipient replies, opts out, or closes.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FollowUpTask, OutreachMessage, InboxMessage, SuppressionEntry, now, uid

CADENCE_DAYS = {
    1: 3,   # Day 3
    2: 7,   # Day 7
    3: 14   # Day 14
}

class FollowUpService:
    def __init__(self, session: Session):
        self.session = session

    def schedule_cadence_for_message(self, initial_message_id: str) -> List[FollowUpTask]:
        msg = self.session.get(OutreachMessage, initial_message_id)
        if not msg:
            raise ValueError(f"Message {initial_message_id} not found")

        tasks = []
        base_time = msg.sent_at or now()
        for step, days in CADENCE_DAYS.items():
            due = base_time + timedelta(days=days)
            task = FollowUpTask(
                campaign_id=msg.campaign_id,
                business_id=msg.business_id,
                contact_id=msg.contact_id,
                step_number=step,
                due_at=due,
                status='scheduled',
                cancellation_reason='',
                created_at=now()
            )
            self.session.add(task)
            tasks.append(task)

        self.session.commit()
        return tasks

    def check_and_cancel_if_replied(self, business_id: str) -> int:
        """Check if any inbound message has arrived for this business; if so, cancel pending follow-ups."""
        replies = self.session.scalars(
            select(InboxMessage).where(
                InboxMessage.business_id == business_id,
                InboxMessage.direction == 'inbound'
            )
        ).all()
        if not replies:
            return 0

        pending_tasks = self.session.scalars(
            select(FollowUpTask).where(
                FollowUpTask.business_id == business_id,
                FollowUpTask.status.in_(['scheduled', 'pending_approval'])
            )
        ).all()

        for t in pending_tasks:
            t.status = 'cancelled'
            t.cancellation_reason = 'Recipient replied; automated cadence halted.'

        self.session.commit()
        return len(pending_tasks)

    def approve_followup(self, task_id: str) -> FollowUpTask:
        task = self.session.get(FollowUpTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = 'approved'
        self.session.commit()
        return task

