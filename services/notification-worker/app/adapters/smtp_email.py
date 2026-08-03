import smtplib
from email.mime.text import MIMEText

from ..config import settings
from .base import NotificationAdapter, NotificationMessage


class SmtpEmailAdapter(NotificationAdapter):
    """Real SMTP delivery. Requires smtp_host/username/password to be set via
    server-side environment variables — never hardcoded, never sent to or
    read from any client application."""

    def send(self, message: NotificationMessage) -> None:
        if not settings.smtp_host:
            raise RuntimeError("SMTP_HOST is not configured")
        msg = MIMEText(message.body)
        msg["Subject"] = message.subject
        msg["From"] = settings.smtp_from_address
        msg["To"] = message.to_email

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from_address, [message.to_email], msg.as_string())
