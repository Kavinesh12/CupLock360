import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, new_opaque_token, sha256_hex
from app.models import RefreshToken, User


def find_user_for_login(db: Session, login: str) -> User | None:
    login = login.strip()
    return db.scalar(select(User).where(or_(
        User.username == login.lower(), User.phone == login, User.email == login.lower(),
    )))


def issue_tokens(db: Session, user: User, *, family_id: uuid.UUID | None = None,
                 user_agent: str | None = None, ip: str | None = None) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    raw = new_opaque_token()
    db.add(RefreshToken(
        user_id=user.id, family_id=family_id or uuid.uuid4(), token_hash=sha256_hex(raw),
        issued_at=now, expires_at=now + timedelta(days=s.refresh_token_days),
        user_agent=(user_agent or "")[:300] or None, ip=ip,
    ))
    return {
        "access_token": create_access_token(user.id, user.token_version),
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": s.access_token_minutes * 60,
    }


class RefreshError(Exception):
    pass


def rotate_refresh(db: Session, raw: str, *, user_agent: str | None, ip: str | None) -> tuple[User, dict]:
    """Single-use refresh tokens. Reusing a spent token revokes the whole session family."""
    now = datetime.now(UTC)
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw))
                   .with_for_update())
    if rt is None:
        raise RefreshError("invalid")
    if rt.used_at is not None or rt.revoked_at is not None:
        revoke_family(db, rt.family_id)
        raise RefreshError("reused")
    if now >= rt.expires_at:
        raise RefreshError("expired")
    user = db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise RefreshError("inactive")
    rt.used_at = now
    return user, issue_tokens(db, user, family_id=rt.family_id, user_agent=user_agent, ip=ip)


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken)
               .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=datetime.now(UTC)))


def revoke_all_sessions(db: Session, user: User) -> None:
    """Instant revocation: kills every refresh token and every outstanding access token."""
    db.execute(update(RefreshToken)
               .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=datetime.now(UTC)))
    user.token_version += 1


def mask(value: str | None) -> str | None:
    if not value:
        return None
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:2]}***@{domain}"
    return f"******{value[-4:]}"
