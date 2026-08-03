from ..config import settings
from .base import NotificationAdapter, NotificationMessage


class SendGridEmailAdapter(NotificationAdapter):
    """Requires the `sendgrid` package and SENDGRID_API_KEY. Not installed by
    default to keep the base image small; add `sendgrid` to requirements.txt
    when enabling this adapter in production."""

    def send(self, message: NotificationMessage) -> None:
        if not settings.sendgrid_api_key:
            raise RuntimeError("SENDGRID_API_KEY is not configured")
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
        except ImportError as exc:
            raise RuntimeError(
                "sendgrid package not installed. Run: pip install sendgrid"
            ) from exc

        mail = Mail(
            from_email=settings.smtp_from_address,
            to_emails=message.to_email,
            subject=message.subject,
            plain_text_content=message.body,
        )
        client = SendGridAPIClient(settings.sendgrid_api_key)
        client.send(mail)
