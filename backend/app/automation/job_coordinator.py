"""Automation Coordinator & Background Job Supervisor for SparkXFlow.
Maintains a global execution kill-switch, scheduled autonomous discovery, and job run histories.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AutomationJob, SystemIntegration, SearchJob, now

logger = logging.getLogger('sparkxflow.automation.coordinator')

class AutomationCoordinator:
    def __init__(self, session: Session):
        self.session = session

    def is_autonomous_enabled(self) -> bool:
        """Global kill-switch check for all autonomous tasks."""
        control = self.session.scalars(
            select(SystemIntegration).where(SystemIntegration.service_name == 'autonomous_control')
        ).first()
        if not control:
            control = SystemIntegration(
                service_name='autonomous_control',
                is_enabled=True,
                status='active',
                config_json='{"paused": false}',
                created_at=now()
            )
            self.session.add(control)
            self.session.commit()
            return True
        return control.is_enabled

    def set_autonomous_state(self, enabled: bool) -> bool:
        control = self.session.scalars(
            select(SystemIntegration).where(SystemIntegration.service_name == 'autonomous_control')
        ).first()
        if not control:
            control = SystemIntegration(
                service_name='autonomous_control',
                is_enabled=enabled,
                status='active' if enabled else 'paused',
                config_json=f'{{"paused": {str(not enabled).lower()}}}',
                created_at=now()
            )
            self.session.add(control)
        else:
            control.is_enabled = enabled
            control.status = 'active' if enabled else 'paused'
            control.config_json = f'{{"paused": {str(not enabled).lower()}}}'
        self.session.commit()
        return control.is_enabled

    def list_jobs(self) -> List[AutomationJob]:
        return list(self.session.scalars(
            select(AutomationJob).order_by(AutomationJob.created_at.desc())
        ).all())

    def register_default_jobs(self):
        defaults = [
            ("autonomous_discovery", "Daily Autonomous Lead Discovery", "0 9 * * *"),
            ("followup_cadence", "Follow-up Cadence Supervisor", "0 */6 * * *"),
            ("sheets_sync", "Google Sheets Scheduled Working View Sync", "0 */4 * * *")
        ]
        for jtype, name, cron in defaults:
            existing = self.session.scalars(
                select(AutomationJob).where(AutomationJob.job_type == jtype)
            ).first()
            if not existing:
                self.session.add(AutomationJob(
                    job_type=jtype,
                    name=name,
                    schedule_cron=cron,
                    is_active=True,
                    last_status='idle',
                    created_at=now()
                ))
        self.session.commit()

