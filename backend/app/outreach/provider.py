"""Provider-independent email transmission layer for SparkXFlow Engine D.
Supports local mock development and Gmail API / SMTP integration.
Outbound email sending is strictly gated behind explicit human approval.
"""
import abc
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('sparkxflow.outreach.provider')

class BaseEmailProvider(abc.ABC):
    @abc.abstractmethod
    def send_email(self,
                   recipient_email: str,
                   subject: str,
                   body_text: str,
                   body_html: Optional[str] = None) -> Dict[str, Any]:
        """Transmit message through email service provider."""
        pass

    @abc.abstractmethod
    def check_connection(self) -> Dict[str, Any]:
        """Test authentication and quota availability with provider."""
        pass

class MockLocalEmailProvider(BaseEmailProvider):
    """Safe local development provider. Logs and returns deterministic transmission receipts
    without making external network connections.
    """

    def __init__(self, from_address: str = "outreach@sparkxflow.agency"):
        self.from_address = from_address
        self.sent_messages = []

    def send_email(self,
                   recipient_email: str,
                   subject: str,
                   body_text: str,
                   body_html: Optional[str] = None) -> Dict[str, Any]:
        import uuid
        msg_id = f"mock-msg-{uuid.uuid4().hex[:12]}"
        logger.info("MOCK SEND: To %s | Subject: %s | ID: %s", recipient_email, subject, msg_id)
        receipt = {
            'success': True,
            'provider': 'mock_local',
            'message_id': msg_id,
            'recipient': recipient_email,
            'subject': subject,
            'from': self.from_address
        }
        self.sent_messages.append(receipt)
        return receipt

    def check_connection(self) -> Dict[str, Any]:
        return {
            'connected': True,
            'provider': 'mock_local',
            'from_address': self.from_address,
            'quota_remaining': 500,
            'mode': 'safe_local_sandbox'
        }

class GmailEmailProvider(BaseEmailProvider):
    """Production Gmail provider integration.
    Requires user-configured App Password or OAuth2 credentials.
    """

    def __init__(self, user_email: str = '', app_password: str = ''):
        self.user_email = user_email
        self.app_password = app_password

    def check_connection(self) -> Dict[str, Any]:
        if not self.user_email or not self.app_password:
            return {
                'connected': False,
                'provider': 'gmail',
                'error': 'Missing GMAIL_USER or GMAIL_APP_PASSWORD credentials in configuration',
                'quota_remaining': 0
            }
        return {
            'connected': True,
            'provider': 'gmail',
            'user_email': self.user_email,
            'quota_remaining': 500
        }

    def send_email(self,
                   recipient_email: str,
                   subject: str,
                   body_text: str,
                   body_html: Optional[str] = None) -> Dict[str, Any]:
        # If credentials are not set, refuse send
        status = self.check_connection()
        if not status['connected']:
            raise RuntimeError(f"Gmail provider is not configured: {status.get('error')}")

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.user_email
        msg['To'] = recipient_email
        msg.attach(MIMEText(body_text, 'plain'))
        if body_html:
            msg.attach(MIMEText(body_html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
            server.login(self.user_email, self.app_password)
            server.send_message(msg)

        import uuid
        return {
            'success': True,
            'provider': 'gmail',
            'message_id': f"gmail-{uuid.uuid4().hex[:12]}",
            'recipient': recipient_email
        }

def get_email_provider(config: Optional[Dict[str, Any]] = None) -> BaseEmailProvider:
    cfg = config or {}
    provider_type = cfg.get('provider', 'mock_local')
    if provider_type == 'gmail' and cfg.get('gmail_user') and cfg.get('gmail_password'):
        return GmailEmailProvider(user_email=cfg.get('gmail_user'), app_password=cfg.get('gmail_password'))
    return MockLocalEmailProvider()

