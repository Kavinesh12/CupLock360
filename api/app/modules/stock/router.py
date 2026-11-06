from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, in_scope, require, scope_ids
from app.models import (
    Item,
    Site,
    StockBalance,
    StockCheck,
    StockCheckLine,
    StockEntry,
    StockMovement,
    Transfer,
    TransferLine,
    User,
    Warehouse,
)
from app.models.stock import STATUSES
from app.modules.stock import opening
from app.services import audit, stock

router = APIRouter(prefix="/stock", tags=["stock"])


# ---------- helpers ----------


def _warehouse(db: Session, user: User, warehouse_id: int) -> Warehouse:
    w = db.get(Warehouse, warehouse_id)
    wh_scope = scope_ids(user, "warehouse")
    if not w or not in_scope(user, branch_id=w.branch_id) or (wh_scope is not None and w.id not in wh_scope):
        raise HTTPException(404, "Warehouse not found")
    return w


def _visible_warehouse_ids(db: Session, user: User) -> list[int]:
    stmt = select(Warehouse.id)
    if (b := scope_ids(user, "branch")) is not None:
        stmt = stmt.where(Warehouse.branch_id.in_(b))
    if (w := scope_ids(user, "warehouse")) is not None:
        stmt = stmt.where(Warehouse.id.in_(w))
    return list(db.scalars(stmt))


def _stock_http(e: stock.StockError) -> HTTPException:
    return HTTPException(409, {"code": "stock", "message": e.message, "shortages": e.shortages})


def _check_items(db: Session, ids: list[int]) -> dict[int, Item]:
    found = {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(ids)))}
    if missing := set(ids) - found.keys():
        raise HTTPException(422, f"Unknown item id(s): {sorted(missing)}")
    return found


# ---------- schemas ----------


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    location_type: str
    location_id: int
    item_id: int
    status: str
    qty: int


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ref_no: str
    kind: str
    warehouse_id: int | None
    reason: str | None
    note: str | None
    source_type: str | None
    source_id: int | None
    created_by: int
    created_at: datetime
    entries: list[EntryOut]


class StatusChangeIn(BaseModel):
    warehouse_id: int
    item_id: int
    from_status: str
    to_status: str
    qty: int = Field(gt=0)
    reason: str | None = None


class WriteOffIn(BaseModel):
    warehouse_id: int
    item_id: int
    from_status: str
    qty: int = Field(gt=0)
    reason: str = Field(min_length=3)


class TransferLineIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0)


class TransferIn(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    vehicle_no: str | None = None
    note: str | None = None
    lines: list[TransferLineIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValueError("From and to warehouse must differ")
        if len({ln.item_id for ln in self.lines}) != len(self.lines):
            raise ValueError("An item appears twice")
        return self


class ReceiveLineIn(BaseModel):
    item_id: int
    received: int = Field(ge=0)
    damaged: int = Field(default=0, ge=0)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLineIn]
    note: str | None = None


class TransferLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    qty_sent: int
    qty_received: int | None
    qty_damaged: int | None
    qty_missing: int | None


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ref_no: str
    from_warehouse_id: int
    to_warehouse_id: int
    status: str
    vehicle_no: str | None
    note: str | None
    sent_by: int
    sent_at: datetime
    received_by: int | None
    received_at: datetime | None
    lines: list[TransferLineOut]


class CheckLineIn(BaseModel):
    item_id: int
    counted: int = Field(ge=0)


class CheckIn(BaseModel):
    warehouse_id: int
    note: str | None = None
    lines: list[CheckLineIn] = Field(min_length=1)


class CheckLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    system_qty: int
    counted_qty: int
    variance: int


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ref_no: str
    warehouse_id: int
    status_counted: str
    note: str | None
    counted_by: int
    counted_at: datetime
    lines: list[CheckLineOut]


# ---------- views ----------


@router.get("/meta")
def meta(_: User = Depends(require("stock.view"))):
    return {
        "statuses": STATUSES,
        "transitions": [{"from": a, "to": b, "label": lbl} for (a, b), lbl in stock.TRANSITIONS.items()],
        "write_off_from": stock.WRITE_OFF_FROM,
    }


@router.get("/warehouses")
def stock_warehouses(db: Session = Depends(get_db), user: User = Depends(require("stock.view"))):
    """All active warehouses (transfer destinations); `mine` marks those the user can work in."""
    mine = set(_visible_warehouse_ids(db, user))
    whs = db.scalars(select(Warehouse).where(Warehouse.is_active).order_by(Warehouse.code))
    return [{"id": w.id, "code": w.code, "name": w.name, "branch_id": w.branch_id, "mine": w.id in mine} for w in whs]


@router.get("/summary")
def summary(
    warehouse_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require("stock.view"))
):
    """Per item: quantity in each status. Warehouses in scope, plus in-transit and at-site totals."""
    wh_ids = [_warehouse(db, user, warehouse_id).id] if warehouse_id else _visible_warehouse_ids(db, user)
    rows = db.execute(
        select(StockBalance.item_id, StockBalance.status, func.sum(StockBalance.qty))
        .where(StockBalance.location_type == "warehouse", StockBalance.location_id.in_(wh_ids))
        .group_by(StockBalance.item_id, StockBalance.status)
    ).all()
    out: dict[int, dict] = {}
    for item_id, status, q in rows:
        out.setdefault(item_id, {s: 0 for s in STATUSES})[status] += int(q)
    if not warehouse_id:
        for loc in ("transit", "site"):
            for item_id, status, q in db.execute(
                select(StockBalance.item_id, StockBalance.status, func.sum(StockBalance.qty))
                .where(StockBalance.location_type == loc)
                .group_by(StockBalance.item_id, StockBalance.status)
            ):
                out.setdefault(item_id, {s: 0 for s in STATUSES})[status] += int(q)
    items = {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(out.keys())))}
    result = []
    for item_id, by_status in sorted(out.items(), key=lambda kv: items[kv[0]].code):
        total = sum(by_status.values())
        if total == 0:
            continue
        it = items[item_id]
        result.append(
            {
                "item_id": item_id,
                "item_code": it.code,
                "item_name": it.name,
                "category": it.category,
                **by_status,
                "total": total,
            }
        )
    return result


@router.get("/by-location")
def by_location(
    item_id: int | None = None,
    location_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.view")),
):
    """Non-zero balances per location, item and status. Used for 'where is it?' lookups."""
    stmt = select(StockBalance).where(StockBalance.qty > 0)
    if item_id:
        stmt = stmt.where(StockBalance.item_id == item_id)
    if location_type:
        stmt = stmt.where(StockBalance.location_type == location_type)
    wh_ids = set(_visible_warehouse_ids(db, user))
    whs = {w.id: w for w in db.scalars(select(Warehouse))}
    sites = {s.id: s for s in db.scalars(select(Site))}
    transfers = {t.id: t for t in db.scalars(select(Transfer).where(Transfer.status == "in_transit"))}
    items = {i.id: i for i in db.scalars(select(Item))}
    out = []
    for b in db.scalars(stmt):
        if b.location_type == "warehouse":
            if b.location_id not in wh_ids:
                continue
            name = f"{whs[b.location_id].code} · {whs[b.location_id].name}"
        elif b.location_type == "site":
            s = sites.get(b.location_id)
            name = f"{s.code} · {s.name}" if s else f"Site {b.location_id}"
        else:
            t = transfers.get(b.location_id)
            name = f"In transit {t.ref_no}" if t else f"Transit {b.location_id}"
        it = items[b.item_id]
        out.append(
            {
                "location_type": b.location_type,
                "location_id": b.location_id,
                "location_name": name,
                "item_id": b.item_id,
                "item_code": it.code,
                "item_name": it.name,
                "status": b.status,
                "qty": b.qty,
            }
        )
    out.sort(key=lambda r: (r["item_code"], r["location_type"], r["location_name"], r["status"]))
    return out


@router.get("/movements", response_model=list[MovementOut])
def movements(
    warehouse_id: int | None = None,
    item_id: int | None = None,
    kind: str | None = None,
    before_id: int | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.view")),
):
    stmt = select(StockMovement).order_by(StockMovement.id.desc()).limit(limit)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == _warehouse(db, user, warehouse_id).id)
    elif scope_ids(user, "branch") is not None or scope_ids(user, "warehouse") is not None:
        stmt = stmt.where(StockMovement.warehouse_id.in_(_visible_warehouse_ids(db, user)))
    if item_id:
        stmt = stmt.where(StockMovement.id.in_(select(StockEntry.movement_id).where(StockEntry.item_id == item_id)))
    if kind:
        stmt = stmt.where(StockMovement.kind == kind)
    if before_id:
        stmt = stmt.where(StockMovement.id < before_id)
    return list(db.scalars(stmt))


# ---------- opening stock ----------


@router.get("/opening/template")
def opening_template(db: Session = Depends(get_db), _: User = Depends(require("stock.adjust"))):
    return Response(
        opening.template(db),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cuplock360-opening-stock.xlsx"'},
    )


@router.post("/opening/import")
async def opening_import(
    request: Request,
    file: UploadFile = File(...),
    commit: bool = Form(False),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.adjust")),
):
    """Upload the filled template. commit=false (default) only validates and previews."""
    content = await file.read()
    if len(content) > 5_000_000:
        raise HTTPException(413, "File too large (max 5 MB)")
    parsed = opening.parse(db, user, content)
    if not commit or not parsed["ok"]:
        return {**parsed, "committed": False}
    try:
        mvs = opening.commit(db, user, parsed, note)
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    audit.record(
        db,
        "stock.opening_imported",
        user_id=user.id,
        entity="stock_movement",
        entity_id=",".join(m.ref_no for m in mvs),
        data={"file": file.filename, "rows": len(parsed["rows"]), "totals": parsed["totals"]},
        ip=client_ip(request),
    )
    db.commit()
    return {**parsed, "committed": True, "movements": [m.ref_no for m in mvs]}


# ---------- status changes & write-offs ----------


@router.post("/status-change", response_model=MovementOut, status_code=201)
def status_change(
    body: StatusChangeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.move")),
    idempotency_key: str | None = Header(default=None),
):
    w = _warehouse(db, user, body.warehouse_id)
    if (done := stock.replay(db, idempotency_key)) and done.kind == "status_change":
        return done
    _check_items(db, [body.item_id])
    label = stock.TRANSITIONS.get((body.from_status, body.to_status))
    if not label:
        raise HTTPException(422, f"Cannot move stock from {body.from_status} to {body.to_status}")
    if body.to_status == "missing" and "stock.adjust" not in user.permission_codes:
        raise HTTPException(403, "Marking stock missing needs stock.adjust")
    try:
        mv = stock.post(
            db,
            kind="status_change",
            warehouse_id=w.id,
            user_id=user.id,
            reason=body.reason or label,
            idempotency_key=idempotency_key,
            lines=stock.move(("warehouse", w.id), body.item_id, body.qty, body.from_status, body.to_status),
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    audit.record(
        db,
        "stock.status_changed",
        user_id=user.id,
        entity="stock_movement",
        entity_id=mv.ref_no,
        data=body.model_dump(),
        ip=client_ip(request),
    )
    db.commit()
    return mv


@router.post("/write-off", response_model=MovementOut, status_code=201)
def write_off(
    body: WriteOffIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("stock.adjust"))
):
    w = _warehouse(db, user, body.warehouse_id)
    _check_items(db, [body.item_id])
    if body.from_status not in stock.WRITE_OFF_FROM:
        raise HTTPException(422, "Only damaged or missing stock can be written off")
    try:
        mv = stock.post(
            db,
            kind="write_off",
            warehouse_id=w.id,
            user_id=user.id,
            reason=body.reason,
            lines=[stock.Line("warehouse", w.id, body.item_id, body.from_status, -body.qty)],
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    audit.record(
        db,
        "stock.written_off",
        user_id=user.id,
        entity="stock_movement",
        entity_id=mv.ref_no,
        data=body.model_dump(),
        ip=client_ip(request),
    )
    db.commit()
    return mv


# ---------- transfers ----------


def _visible_transfers(db: Session, user: User):
    ids = _visible_warehouse_ids(db, user)
    return select(Transfer).where((Transfer.from_warehouse_id.in_(ids)) | (Transfer.to_warehouse_id.in_(ids)))


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(
    status: str | None = None, db: Session = Depends(get_db), user: User = Depends(require("stock.view"))
):
    stmt = _visible_transfers(db, user).order_by(Transfer.id.desc()).limit(200)
    if status:
        stmt = stmt.where(Transfer.status == status)
    return list(db.scalars(stmt))


@router.post("/transfers", response_model=TransferOut, status_code=201)
def send_transfer(
    body: TransferIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.move")),
    idempotency_key: str | None = Header(default=None),
):
    src = _warehouse(db, user, body.from_warehouse_id)
    if (done := stock.replay(db, idempotency_key)) and done.source_type == "transfer":
        return db.get(Transfer, done.source_id)
    dst = db.get(Warehouse, body.to_warehouse_id)
    if not dst or not dst.is_active:
        raise HTTPException(422, "Destination warehouse not found")
    _check_items(db, [ln.item_id for ln in body.lines])
    n = db.scalar(select(func.count()).select_from(Transfer)) + 1
    t = Transfer(
        ref_no=f"TRF-{n:06d}",
        from_warehouse_id=src.id,
        to_warehouse_id=dst.id,
        vehicle_no=body.vehicle_no,
        note=body.note,
        sent_by=user.id,
        status="in_transit",
        lines=[TransferLine(item_id=ln.item_id, qty_sent=ln.qty) for ln in body.lines],
    )
    db.add(t)
    db.flush()
    lines = []
    for ln in body.lines:
        lines += stock.move(
            ("warehouse", src.id), ln.item_id, ln.qty, "available", "in_transit", to_location=("transit", t.id)
        )
    try:
        stock.post(
            db,
            kind="transfer_send",
            warehouse_id=src.id,
            user_id=user.id,
            source=("transfer", t.id),
            reason=f"Transfer {t.ref_no} to {dst.code}",
            idempotency_key=idempotency_key,
            lines=lines,
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    audit.record(
        db,
        "stock.transfer_sent",
        user_id=user.id,
        entity="transfer",
        entity_id=t.ref_no,
        data=body.model_dump(),
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(t)
    return t


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
def receive_transfer(
    transfer_id: int,
    body: ReceiveIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("stock.move")),
):
    """Received goes to available at the destination, damaged to damaged there; any shortfall is
    recorded as missing at the sending warehouse (it left from there)."""
    t = db.get(Transfer, transfer_id, with_for_update=True)
    if not t:
        raise HTTPException(404, "Transfer not found")
    dst = _warehouse(db, user, t.to_warehouse_id)
    if t.status != "in_transit":
        raise HTTPException(400, f"Transfer is already {t.status}")
    got = {ln.item_id: ln for ln in body.lines}
    if extra := set(got) - {ln.item_id for ln in t.lines}:
        raise HTTPException(422, f"Item(s) not on this transfer: {sorted(extra)}")
    lines = []
    for tl in t.lines:
        r = got.get(tl.item_id)
        received, damaged = (r.received, r.damaged) if r else (0, 0)
        if received + damaged > tl.qty_sent:
            raise HTTPException(422, f"Item {tl.item_id}: received + damaged is more than sent ({tl.qty_sent})")
        missing = tl.qty_sent - received - damaged
        tl.qty_received, tl.qty_damaged, tl.qty_missing = received, damaged, missing
        transit = ("transit", t.id)
        if received:
            lines += stock.move(transit, tl.item_id, received, "in_transit", "available", ("warehouse", dst.id))
        if damaged:
            lines += stock.move(transit, tl.item_id, damaged, "in_transit", "damaged", ("warehouse", dst.id))
        if missing:
            lines += stock.move(
                transit, tl.item_id, missing, "in_transit", "missing", ("warehouse", t.from_warehouse_id)
            )
    try:
        stock.post(
            db,
            kind="transfer_receive",
            warehouse_id=dst.id,
            user_id=user.id,
            source=("transfer", t.id),
            reason=f"Received {t.ref_no}",
            note=body.note,
            lines=lines,
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    t.status, t.received_by, t.received_at = "received", user.id, datetime.now(UTC)
    audit.record(
        db,
        "stock.transfer_received",
        user_id=user.id,
        entity="transfer",
        entity_id=t.ref_no,
        data=body.model_dump(),
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(t)
    return t


# ---------- stock check ----------


@router.get("/checks", response_model=list[CheckOut])
def list_checks(
    warehouse_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require("stock.view"))
):
    stmt = select(StockCheck).where(StockCheck.warehouse_id.in_(_visible_warehouse_ids(db, user)))
    if warehouse_id:
        stmt = stmt.where(StockCheck.warehouse_id == warehouse_id)
    return list(db.scalars(stmt.order_by(StockCheck.id.desc()).limit(100)))


@router.post("/checks", response_model=CheckOut, status_code=201)
def post_check(
    body: CheckIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("stock.adjust"))
):
    """Physical count of available stock. Short = available -> missing; extra = missing -> available
    first, any remainder is booked as found stock."""
    w = _warehouse(db, user, body.warehouse_id)
    if len({ln.item_id for ln in body.lines}) != len(body.lines):
        raise HTTPException(422, "An item appears twice")
    _check_items(db, [ln.item_id for ln in body.lines])
    n = db.scalar(select(func.count()).select_from(StockCheck)) + 1
    chk = StockCheck(ref_no=f"SCK-{n:06d}", warehouse_id=w.id, note=body.note, counted_by=user.id)
    db.add(chk)
    db.flush()
    loc = ("warehouse", w.id)
    lines: list[stock.Line] = []
    for ln in body.lines:
        sys_qty = stock.balance(db, loc, ln.item_id, "available")
        var = ln.counted - sys_qty
        chk.lines.append(StockCheckLine(item_id=ln.item_id, system_qty=sys_qty, counted_qty=ln.counted, variance=var))
        if var < 0:
            lines += stock.move(loc, ln.item_id, -var, "available", "missing")
        elif var > 0:
            from_missing = min(var, stock.balance(db, loc, ln.item_id, "missing"))
            if from_missing:
                lines += stock.move(loc, ln.item_id, from_missing, "missing", "available")
            if var - from_missing:
                lines.append(stock.Line("warehouse", w.id, ln.item_id, "available", var - from_missing))
    if lines:
        try:
            stock.post(
                db,
                kind="stock_check",
                warehouse_id=w.id,
                user_id=user.id,
                source=("stock_check", chk.id),
                reason=f"Stock check {chk.ref_no}",
                note=body.note,
                lines=lines,
            )
        except stock.StockError as e:
            db.rollback()
            raise _stock_http(e) from None
    variances = defaultdict(int)
    for ln in chk.lines:
        variances["short" if ln.variance < 0 else "extra"] += abs(ln.variance)
    audit.record(
        db,
        "stock.check_posted",
        user_id=user.id,
        entity="stock_check",
        entity_id=chk.ref_no,
        data={"warehouse_id": w.id, "items": len(body.lines), **variances},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(chk)
    return chk
