from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, require
from app.models import Branch, User, Warehouse
from app.services import audit

router = APIRouter(tags=["branches & warehouses"])


class BranchIn(BaseModel):
    code: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    name: str = Field(min_length=1, max_length=120)
    city: str | None = None
    state: str = "Tamil Nadu"
    gstin: str | None = Field(default=None, pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    address: str | None = None
    is_active: bool = True


class BranchOut(BranchIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class WarehouseIn(BaseModel):
    branch_id: int
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    address: str | None = None
    is_active: bool = True


class WarehouseOut(WarehouseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


def _scoped_branch_ids(user: User) -> set[int] | None:
    ids = {s.scope_id for s in user.scopes if s.scope_type == "branch"}
    return ids or None


@router.get("/branches", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db), user: User = Depends(require("branches.view"))):
    stmt = select(Branch).order_by(Branch.name)
    if (ids := _scoped_branch_ids(user)) is not None:
        stmt = stmt.where(Branch.id.in_(ids))
    return list(db.scalars(stmt))


@router.post("/branches", response_model=BranchOut, status_code=201)
def create_branch(body: BranchIn, request: Request, db: Session = Depends(get_db),
                  actor: User = Depends(require("branches.manage"))):
    b = Branch(**body.model_dump())
    db.add(b)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Branch code already exists") from None
    audit.record(db, "branch.created", user_id=actor.id, entity="branch", entity_id=b.id,
                 data=body.model_dump(), ip=client_ip(request))
    db.commit()
    return b


@router.put("/branches/{branch_id}", response_model=BranchOut)
def update_branch(branch_id: int, body: BranchIn, request: Request, db: Session = Depends(get_db),
                  actor: User = Depends(require("branches.manage"))):
    b = db.get(Branch, branch_id)
    if not b:
        raise HTTPException(404, "Branch not found")
    before = BranchOut.model_validate(b).model_dump()
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Branch code already exists") from None
    audit.record(db, "branch.updated", user_id=actor.id, entity="branch", entity_id=b.id,
                 data={"before": before, "after": body.model_dump()}, ip=client_ip(request))
    db.commit()
    return b


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(branch_id: int | None = None, db: Session = Depends(get_db),
                    user: User = Depends(require("branches.view"))):
    stmt = select(Warehouse).order_by(Warehouse.name)
    if branch_id:
        stmt = stmt.where(Warehouse.branch_id == branch_id)
    if (ids := _scoped_branch_ids(user)) is not None:
        stmt = stmt.where(Warehouse.branch_id.in_(ids))
    return list(db.scalars(stmt))


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(body: WarehouseIn, request: Request, db: Session = Depends(get_db),
                     actor: User = Depends(require("branches.manage"))):
    if not db.get(Branch, body.branch_id):
        raise HTTPException(422, "Branch not found")
    w = Warehouse(**body.model_dump())
    db.add(w)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Warehouse code already exists") from None
    audit.record(db, "warehouse.created", user_id=actor.id, entity="warehouse", entity_id=w.id,
                 data=body.model_dump(), ip=client_ip(request))
    db.commit()
    return w
