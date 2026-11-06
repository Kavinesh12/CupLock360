from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, in_scope, require
from app.models import Client, Item, Project, RateCard, RateCardLine, User
from app.services import audit
from app.services.rates import effective_rates

router = APIRouter(tags=["items & rates"])

Category = Literal["standard", "ledger", "transom", "jack", "plank", "brace", "accessory", "other"]


class ItemIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9.\-/]+$")
    name: str = Field(min_length=2, max_length=200)
    category: Category
    size_m: Decimal | None = Field(default=None, ge=0)
    unit: str = "nos"
    weight_kg: Decimal | None = Field(default=None, ge=0)
    hsn_sac: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    replacement_cost: Decimal = Field(default=Decimal(0), ge=0)
    is_active: bool = True


class ItemOut(ItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class LineIn(BaseModel):
    item_id: int
    rate_per_day: Decimal = Field(gt=0)
    rate_per_month: Decimal | None = Field(default=None, gt=0)


class LineOut(LineIn):
    model_config = ConfigDict(from_attributes=True)


class RateCardIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    client_id: int | None = None
    project_id: int | None = None
    valid_from: date
    valid_to: date | None = None
    min_days: int = Field(default=30, ge=0, le=365)
    grace_days: int = Field(default=0, ge=0, le=60)
    is_active: bool = True
    lines: list[LineIn] = []

    @model_validator(mode="after")
    def check(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to is before valid_from")
        ids = [ln.item_id for ln in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("An item appears twice on the rate card")
        return self


class RateCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    client_id: int | None
    project_id: int | None
    valid_from: date
    valid_to: date | None
    min_days: int
    grace_days: int
    is_active: bool
    lines: list[LineOut]


class EffectiveRateOut(BaseModel):
    item_id: int
    rate_per_day: Decimal
    rate_per_month: Decimal | None
    min_days: int
    grace_days: int
    rate_card_id: int
    rate_card_name: str
    level: str


# ---------- items ----------

@router.get("/items", response_model=list[ItemOut])
def list_items(q: str | None = None, category: Category | None = None, active: bool | None = None,
               db: Session = Depends(get_db), _: User = Depends(require("items.view"))):
    stmt = select(Item).order_by(Item.category, Item.code)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Item.name).like(like), func.lower(Item.code).like(like)))
    if category:
        stmt = stmt.where(Item.category == category)
    if active is not None:
        stmt = stmt.where(Item.is_active == active)
    return list(db.scalars(stmt))


@router.post("/items", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("items.manage"))):
    it = Item(**body.model_dump())
    db.add(it)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Item code already exists") from None
    audit.record(db, "item.created", user_id=user.id, entity="item", entity_id=it.id,
                 data=body.model_dump(mode="json"), ip=client_ip(request))
    db.commit()
    return it


@router.put("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("items.manage"))):
    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(404, "Item not found")
    before = ItemOut.model_validate(it).model_dump(mode="json")
    for k, v in body.model_dump().items():
        setattr(it, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Item code already exists") from None
    audit.record(db, "item.updated", user_id=user.id, entity="item", entity_id=it.id,
                 data={"before": before, "after": body.model_dump(mode="json")}, ip=client_ip(request))
    db.commit()
    return it


# ---------- rate cards ----------

def _check_card_target(db: Session, user: User, body: RateCardIn) -> None:
    if body.project_id:
        p = db.get(Project, body.project_id)
        if not p:
            raise HTTPException(422, "Project not found")
        if body.client_id and body.client_id != p.client_id:
            raise HTTPException(422, "Project does not belong to that client")
        body.client_id = p.client_id
    if body.client_id:
        c = db.get(Client, body.client_id)
        if not c or not in_scope(user, branch_id=c.branch_id, client_id=c.id):
            raise HTTPException(422, "Client not found")
    found = set(db.scalars(select(Item.id).where(Item.id.in_([ln.item_id for ln in body.lines]))))
    if missing := {ln.item_id for ln in body.lines} - found:
        raise HTTPException(422, f"Unknown item id(s): {sorted(missing)}")


@router.get("/rate-cards", response_model=list[RateCardOut])
def list_rate_cards(client_id: int | None = None, standard_only: bool = False, db: Session = Depends(get_db),
                    _: User = Depends(require("items.view"))):
    stmt = select(RateCard).order_by(RateCard.client_id.nulls_first(), RateCard.valid_from.desc())
    if standard_only:
        stmt = stmt.where(RateCard.client_id.is_(None))
    elif client_id:
        stmt = stmt.where(RateCard.client_id == client_id)
    return list(db.scalars(stmt))


@router.post("/rate-cards", response_model=RateCardOut, status_code=201)
def create_rate_card(body: RateCardIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require("items.manage"))):
    _check_card_target(db, user, body)
    card = RateCard(**body.model_dump(exclude={"lines"}))
    card.lines = [RateCardLine(**ln.model_dump()) for ln in body.lines]
    db.add(card)
    db.flush()
    audit.record(db, "rate_card.created", user_id=user.id, entity="rate_card", entity_id=card.id,
                 data=body.model_dump(mode="json"), ip=client_ip(request))
    db.commit()
    return card


@router.put("/rate-cards/{card_id}", response_model=RateCardOut)
def update_rate_card(card_id: int, body: RateCardIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require("items.manage"))):
    card = db.get(RateCard, card_id)
    if not card:
        raise HTTPException(404, "Rate card not found")
    _check_card_target(db, user, body)
    before = RateCardOut.model_validate(card).model_dump(mode="json")
    for k, v in body.model_dump(exclude={"lines"}).items():
        setattr(card, k, v)
    card.lines = []
    db.flush()
    card.lines = [RateCardLine(**ln.model_dump()) for ln in body.lines]
    db.flush()
    audit.record(db, "rate_card.updated", user_id=user.id, entity="rate_card", entity_id=card.id,
                 data={"before": before, "after": body.model_dump(mode="json")}, ip=client_ip(request))
    db.commit()
    db.refresh(card)
    return card


@router.get("/rates/effective", response_model=list[EffectiveRateOut])
def get_effective_rates(item_ids: list[int] = Query(...), client_id: int | None = None,
                        project_id: int | None = None, on: date | None = None,
                        db: Session = Depends(get_db), _: User = Depends(require("items.view"))):
    rates = effective_rates(db, on=on or date.today(), item_ids=item_ids, client_id=client_id,
                            project_id=project_id)
    return [EffectiveRateOut(**vars(r)) for r in rates.values()]
