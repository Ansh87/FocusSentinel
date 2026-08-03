from ..config import settings
from .base import NotificationAdapter, NotificationMessage


class TwilioSmsAdapter(NotificationAdapter):
    """Requires the `twilio` package and TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN
    / TWILIO_FROM_NUMBER. Not installed by default; add `twilio` to
    requirements.txt when enabling this adapter in production."""

    def send(self, message: NotificationMessage) -> None:
        if not (settings.twilio_account_sid and settings.twilio_auth_token):
            raise RuntimeError("Twilio credentials are not configured")
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise RuntimeError("twilio package not installed. Run: pip install twilio") from exc

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(body=message.body, from_=settings.twilio_from_number, to=message.to_phone)
