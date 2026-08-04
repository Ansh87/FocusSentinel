"""Phone number normalization shared by student-phone registration and the
inbound SMS webhook. Keeping this in one place matters because the webhook
has to match an inbound "From" number against exactly what a parent typed
into the dashboard -- if the two ever normalize differently, texts silently
stop matching anyone.
"""
from __future__ import annotations

import re


def normalize_phone(raw: str) -> str:
    """Best-effort E.164 normalization: strips everything but digits and a
    leading '+', and assumes a bare 10-digit US/Canada number is missing its
    '+1' country code (this app's userbase is US-first; a number already
    given with a country code is left alone). Not a full libphonenumber
    replacement -- good enough to get a consistent key for matching, not a
    claim that the result is a deliverable, dialable number in every case.
    """
    digits = re.sub(r"[^\d+]", "", raw or "")
    if not digits:
        raise ValueError("Phone number is empty after normalization")
    if digits.startswith("+"):
        return digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits
