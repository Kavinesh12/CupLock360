from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, get_current_user
from app.core.security import hash_password, verify_password
from app.models import OtpChallenge, User
from app.modules.auth import service
from app.modules.auth.schemas import (
    LoginIn,
    MeOut,
    OtpChallengeOut,
    RefreshIn,
    TokenOut,
    VerifyOtpIn,
)
from app.services import audit, otp
from app.services.notify import DeliveryError

router = APIRouter(prefix="/auth", tags=["auth"])

_DUMMY_HASH = hash_password("timing-equaliser")


def _otp_http(e: otp.OtpError) -> HTTPException:
    code = status.HTTP_429_TOO_MANY_REQUESTS if e.code == "otp_rate_limited" else status.HTTP_400_BAD_REQUEST
    return HTTPException(code, {"code": e.code, "message": e.message})


@router.post("/login", response_model=OtpChallengeOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    """Step 1: check password, then send an OTP. Tokens are issued only after /auth/verify-otp."""
    ip = client_ip(request)
    user = service.find_user_for_login(db, body.login)
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        audit.record(db, "auth.login_failed", user_id=user.id if user else None, ip=ip,
                     data={"login": body.login[:60]})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid login or password")
    try:
        ch = otp.issue(db, user, "login")
    except otp.OtpError as e:
        db.rollback()
        raise _otp_http(e) from None
    except DeliveryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Could not send OTP: {e}") from None
    audit.record(db, "auth.otp_sent", user_id=user.id, ip=ip, data={"purpose": "login", "channel": ch.channel})
    db.commit()
    sent_to = service.mask(user.email if ch.channel == "email" else user.phone)
    return OtpChallengeOut(challenge_id=ch.id, channel=ch.channel, expires_at=ch.expires_at, sent_to=sent_to)


@router.post("/verify-otp", response_model=TokenOut)
def verify_otp(body: VerifyOtpIn, request: Request, db: Session = Depends(get_db)):
    """Step 2: verify the login OTP and receive access + refresh tokens."""
    ip = client_ip(request)
    try:
        ch = otp.verify(db, body.challenge_id, body.code, purpose="login")
    except otp.OtpError as e:
        ch_row = db.get(OtpChallenge, body.challenge_id)
        audit.record(db, "auth.otp_failed", user_id=ch_row.user_id if ch_row else None, ip=ip,
                     data={"reason": e.code})
        db.commit()
        raise _otp_http(e) from None
    user = db.get(User, ch.user_id)
    if user is None or not user.is_active:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    user.last_login_at = datetime.now(UTC)
    tokens = service.issue_tokens(db, user, user_agent=request.headers.get("user-agent"), ip=ip)
    audit.record(db, "auth.login", user_id=user.id, ip=ip)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    try:
        user, tokens = service.rotate_refresh(db, body.refresh_token,
                                              user_agent=request.headers.get("user-agent"), ip=ip)
    except service.RefreshError as e:
        if str(e) == "reused":
            audit.record(db, "auth.refresh_reuse_detected", ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.") from None
    db.commit()
    return tokens


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.core.security import sha256_hex
    from app.models import RefreshToken

    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(body.refresh_token)))
    if rt:
        service.revoke_family(db, rt.family_id)
        audit.record(db, "auth.logout", user_id=rt.user_id, ip=client_ip(request))
    db.commit()


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(
        id=user.id, username=user.username, full_name=user.full_name, phone=user.phone, email=user.email,
        roles=user.role_codes, permissions=sorted(user.permission_codes),
        scopes=[{"type": s.scope_type, "id": s.scope_id} for s in user.scopes],
        approval_limit=float(user.approval_limit) if user.approval_limit is not None else None,
    )
