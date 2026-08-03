from .base import NotificationAdapter, NotificationMessage


class ConsoleSmsAdapter(NotificationAdapter):
    """Default SMS adapter for local dev/demo — prints instead of sending a
    real text. Swap `sms_provider=twilio` (plus credentials) for real SMS."""

    def send(self, message: NotificationMessage) -> None:
        print(f"[sms:console] to={message.to_phone} body={message.body!r}")
