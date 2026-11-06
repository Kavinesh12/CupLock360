import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog

GENESIS = "0" * 64
_LOCK_KEY = 360_0001  # pg advisory lock id that serialises writes to the chain


def _row_digest(prev_hash: str, at: datetime, user_id: int | None, action: str,
                entity: str | None, entity_id: str | None, data: Any, ip: str | None) -> str:
    body = json.dumps(
        {
            "prev": prev_hash,
            "at": at.isoformat(),
            "user_id": user_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "data": data,
            "ip": ip,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def record(db: Session, action: str, *, user_id: int | None = None, entity: str | None = None,
           entity_id: Any = None, data: dict | None = None, ip: str | None = None) -> AuditLog:
    """Append an audit row in the caller's transaction. Caller commits."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    at = datetime.now(UTC)
    eid = None if entity_id is None else str(entity_id)
    data = json.loads(json.dumps(data, default=str)) if data is not None else None
    row = AuditLog(at=at, user_id=user_id, action=action, entity=entity, entity_id=eid, data=data,
                   ip=ip, prev_hash=prev,
                   hash=_row_digest(prev, at, user_id, action, entity, eid, data, ip))
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, id of first broken row)."""
    prev = GENESIS
    for row in db.scalars(select(AuditLog).order_by(AuditLog.id)).yield_per(1000):
        expected = _row_digest(prev, row.at, row.user_id, row.action, row.entity, row.entity_id,
                               row.data, row.ip)
        if row.prev_hash != prev or row.hash != expected:
            return False, row.id
        prev = row.hash
    return True, None
