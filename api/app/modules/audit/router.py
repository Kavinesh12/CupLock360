from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require
from app.models import AuditLog, User
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: datetime
    user_id: int | None
    action: str
    entity: str | None
    entity_id: str | None
    data: dict | None
    ip: str | None


@router.get("", response_model=list[AuditOut])
def list_audit(action: str | None = None, user_id: int | None = None, before_id: int | None = None,
               limit: int = Query(50, le=200), db: Session = Depends(get_db),
               _: User = Depends(require("audit.view"))):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if before_id:
        stmt = stmt.where(AuditLog.id < before_id)
    return list(db.scalars(stmt))


@router.get("/verify")
def verify(db: Session = Depends(get_db), _: User = Depends(require("audit.view"))):
    ok, broken_at = verify_chain(db)
    return {"ok": ok, "first_broken_id": broken_at}
