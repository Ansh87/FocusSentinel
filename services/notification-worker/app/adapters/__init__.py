from ..config import settings
from .base import NotificationAdapter, NotificationMessage
from .console_email import ConsoleEmailAdapter
from .console_sms import ConsoleSmsAdapter
from .sendgrid_email import SendGridEmailAdapter
from .smtp_email import SmtpEmailAdapter
from .twilio_sms import TwilioSmsAdapter

_EMAIL_ADAPTERS = {
    "console": ConsoleEmailAdapter,
    "smtp": SmtpEmailAdapter,
    "sendgrid": SendGridEmailAdapter,
}
_SMS_ADAPTERS = {
    "console": ConsoleSmsAdapter,
    "twilio": TwilioSmsAdapter,
}


def get_email_adapter() -> NotificationAdapter:
    return _EMAIL_ADAPTERS.get(settings.email_provider, ConsoleEmailAdapter)()


def get_sms_adapter() -> NotificationAdapter:
    return _SMS_ADAPTERS.get(settings.sms_provider, ConsoleSmsAdapter)()


__all__ = ["NotificationAdapter", "NotificationMessage", "get_email_adapter", "get_sms_adapter"]
