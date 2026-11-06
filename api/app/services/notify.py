"""Outbound messages. SMS/WhatsApp gateways plug in here once the client's DLT templates are approved."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.models import User

log = logging.getLogger("cuplock.notify")

# Dev-only outbox so tests and local runs can read OTPs without logging them.
DEV_OUTBOX: list[dict] = []


class DeliveryError(Exception):
    pass


def send_otp(user: User, code: str, purpose: str) -> str:
    """Deliver an OTP. Returns the channel used. Never logs the code."""
    s = get_settings()
    channel = s.otp_delivery
    text = f"{code} is your CUPLOCK 360 OTP for {purpose}. Valid 5 minutes. Do not share it."
    if channel == "console":
        if s.is_prod:
            raise DeliveryError("console delivery disabled in production")
        DEV_OUTBOX.append({"user_id": user.id, "purpose": purpose, "code": code})
        del DEV_OUTBOX[:-50]
        log.info("OTP for user %s (%s) placed in dev outbox", user.id, purpose)
        return channel
    if channel == "email":
        if not user.email:
            raise DeliveryError("user has no email address")
        _send_email(user.email, "Your CUPLOCK 360 OTP", text)
        return channel
    raise DeliveryError(f"OTP channel '{channel}' is not configured yet")


def _send_email(to: str, subject: str, body: str) -> None:
    import os

    host = os.environ.get("CUPLOCK_SMTP_HOST")
    if not host:
        raise DeliveryError("CUPLOCK_SMTP_HOST is not set")
    msg = EmailMessage()
    msg["From"] = os.environ.get("CUPLOCK_SMTP_FROM", "no-reply@cuplock360.local")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("CUPLOCK_SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        user, pw = os.environ.get("CUPLOCK_SMTP_USER"), os.environ.get("CUPLOCK_SMTP_PASSWORD")
        if user and pw:
            smtp.login(user, pw)
        smtp.send_message(msg)
