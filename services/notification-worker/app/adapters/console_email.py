from .base import NotificationAdapter, NotificationMessage


class ConsoleEmailAdapter(NotificationAdapter):
    """Default adapter for local dev/demo: writes the notification to stdout
    instead of sending real email. This is real, working code — it genuinely
    delivers the notification to wherever the worker's logs go — it just
    isn't hooked up to an external mail provider. Swap `email_provider` in
    the environment to 'smtp' or 'sendgrid' for real delivery.
    """

    def send(self, message: NotificationMessage) -> None:
        print(f"[email:console] to={message.to_email} subject={message.subject!r}\n{message.body}\n")
