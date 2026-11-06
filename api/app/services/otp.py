"""Transaction-bound OTP (client deck, slide 8).

- generated and verified by the backend
- 5-minute expiry, single use, 3 attempts
- rate-limited per user
- stored only as a keyed hash, never logged
- bound to purpose + transaction_ref; a changed transaction needs a new OTP
"""

import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_otp_code, otp_hash
from app.models import OtpChallenge, User
from app.services import notify


class OtpError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def issue(db: Session, user: User, purpose: str, transaction_ref: str | None = None) -> OtpChallenge:
    s = get_settings()
    now = datetime.now(UTC)
    recent = db.scalar(
        select(func.count()).select_from(OtpChallenge).where(
            OtpChallenge.user_id == user.id,
            OtpChallenge.created_at > now - timedelta(minutes=s.otp_window_minutes),
        )
    )
    if recent >= s.otp_max_per_window:
        raise OtpError("otp_rate_limited", "Too many OTP requests. Try again in a few minutes.")

    # Any earlier unused OTP for the same purpose/transaction is voided.
    for old in db.scalars(select(OtpChallenge).where(
        OtpChallenge.user_id == user.id,
        OtpChallenge.purpose == purpose,
        OtpChallenge.transaction_ref.is_not_distinct_from(transaction_ref),
        OtpChallenge.consumed_at.is_(None),
    )):
        old.consumed_at = now

    cid = uuid.uuid4()
    code = generate_otp_code()
    ch = OtpChallenge(
        id=cid, user_id=user.id, purpose=purpose, transaction_ref=transaction_ref,
        code_hash=otp_hash(str(cid), code), channel=s.otp_delivery, attempts=0,
        created_at=now, expires_at=now + timedelta(seconds=s.otp_ttl_seconds),
    )
    db.add(ch)
    db.flush()
    ch.channel = notify.send_otp(user, code, purpose)
    return ch


def verify(db: Session, challenge_id: uuid.UUID, code: str, *, purpose: str,
           transaction_ref: str | None = None) -> OtpChallenge:
    """Verify and consume. Caller commits (also on failure, so attempts are counted)."""
    s = get_settings()
    now = datetime.now(UTC)
    ch = db.get(OtpChallenge, challenge_id, with_for_update=True)
    if ch is None or ch.purpose != purpose:
        raise OtpError("otp_invalid", "OTP is invalid.")
    if ch.transaction_ref != transaction_ref:
        raise OtpError("otp_wrong_transaction", "This OTP was issued for a different transaction.")
    if ch.consumed_at is not None:
        raise OtpError("otp_used", "This OTP has already been used. Request a new one.")
    if now >= ch.expires_at:
        raise OtpError("otp_expired", "OTP has expired. Request a new one.")
    if ch.attempts >= s.otp_max_attempts:
        raise OtpError("otp_locked", "Too many wrong attempts. Request a new OTP.")
    ch.attempts += 1
    if not hmac.compare_digest(otp_hash(str(ch.id), code.strip()), ch.code_hash):
        if ch.attempts >= s.otp_max_attempts:
            ch.consumed_at = now
        raise OtpError("otp_invalid", "OTP is invalid.")
    ch.consumed_at = now
    return ch
