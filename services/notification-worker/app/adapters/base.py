from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NotificationMessage:
    subject: str
    body: str
    to_email: str | None = None
    to_phone: str | None = None


class NotificationAdapter(ABC):
    """Every provider (email or SMS) implements this interface so the worker
    loop never branches on vendor-specific logic. Swapping SendGrid for SES,
    or Twilio for another SMS vendor, means adding one adapter file — nothing
    else in the worker changes. Credentials are read from server-side env
    vars only (see config.py); no adapter ever receives a client-supplied key.
    """

    @abstractmethod
    def send(self, message: NotificationMessage) -> None:
        """Raises on failure; the worker marks the notification_event 'failed'
        and leaves it for retry/inspection rather than swallowing errors."""
