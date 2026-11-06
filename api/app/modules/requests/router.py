import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, get_current_user, in_scope, require, scope_ids
from app.models import (
    Branch,
    Client,
    Dispatch,
    DispatchLine,
    MaterialRequest,
    Project,
    RequestLine,
    Site,
    User,
    Warehouse,
)
from app.models.requests import OPEN_STATUSES
from app.modules.auth.service import mask
from app.modules.requests import challan
from app.services import audit, otp, stock
from app.services import requests as svc

router = APIRouter(tags=["requests"])

OTP_PURPOSE = "request_approval"


# ---------- schemas ----------


class LineIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0)


def _unique(lines):
    if len({ln.item_id for ln in lines}) != len(lines):
        raise ValueError("An item appears twice")
    return lines


class RequestIn(BaseModel):
    site_id: int
    warehouse_id: int
    required_on: date
    duration_days: int = Field(ge=1, le=3650)
    transport_charge: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    note: str | None = None
    lines: list[LineIn] = Field(min_length=1)

    _u = field_validator("lines")(_unique)


class EstimateIn(BaseModel):
    site_id: int
    duration_days: int = Field(ge=1, le=3650)
    transport_charge: Decimal = Field(default=Decimal(0), ge=0)
    warehouse_id: int | None = None
    lines: list[LineIn] = Field(min_length=1)

    _u = field_validator("lines")(_unique)


class ApproveLine(BaseModel):
    item_id: int
    qty: int = Field(ge=0)


class OtpRequestIn(BaseModel):
    lines: list[ApproveLine] = Field(min_length=1)


class ApproveIn(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)
    lines: list[ApproveLine] = Field(min_length=1)
    note: str | None = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class DispatchIn(BaseModel):
    vehicle_no: str | None = Field(default=None, max_length=20)
    driver_name: str | None = None
    driver_phone: str | None = Field(default=None, max_length=15)
    note: str | None = None
    lines: list[LineIn] = Field(min_length=1)

    _u = field_validator("lines")(_unique)


class ReceiveLine(BaseModel):
    item_id: int
    received: int = Field(ge=0)


class ReceiveIn(BaseModel):
    receiver_name: str = Field(min_length=2)
    note: str | None = None
    lines: list[ReceiveLine]


class RequestLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    qty_requested: int
    qty_approved: int | None
    qty_dispatched: int
    rate_per_day: Decimal


class DispatchLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    qty: int
    qty_received: int | None
    qty_short: int | None


class DispatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    challan_no: str
    request_id: int
    warehouse_id: int
    site_id: int
    status: str
    vehicle_no: str | None
    driver_name: str | None
    driver_phone: str | None
    note: str | None
    dispatched_by: int
    dispatched_at: datetime
    received_by: int | None
    received_at: datetime | None
    receiver_name: str | None
    receipt_note: str | None
    site_name: str
    request_ref: str
    lines: list[DispatchLineOut]


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ref_no: str
    client_id: int
    project_id: int
    site_id: int
    branch_id: int
    warehouse_id: int
    status: str
    version: int
    required_on: date
    duration_days: int
    transport_charge: Decimal
    est_rent: Decimal
    est_taxable: Decimal
    est_gst: Decimal
    est_total: Decimal
    note: str | None
    created_by: int
    created_at: datetime
    approved_by: int | None
    approved_at: datetime | None
    decision_note: str | None
    client_name: str
    site_name: str
    warehouse_code: str
    lines: list[RequestLineOut]
    dispatches: list[DispatchOut]


# ---------- helpers ----------


def _site_chain(db: Session, user: User, site_id: int) -> tuple[Site, Project, Client]:
    site = db.get(Site, site_id)
    if not site or not site.is_active:
        raise HTTPException(404, "Site not found")
    proj = site.project
    cl = proj.client
    if not in_scope(user, branch_id=proj.branch_id, client_id=cl.id, site_id=site.id):
        raise HTTPException(404, "Site not found")
    return site, proj, cl


def _warehouse(db: Session, warehouse_id: int) -> Warehouse:
    w = db.get(Warehouse, warehouse_id)
    if not w or not w.is_active:
        raise HTTPException(422, "Warehouse not found")
    return w


def _get(db: Session, user: User, request_id: int, lock: bool = False) -> MaterialRequest:
    r = db.get(MaterialRequest, request_id, with_for_update=lock)
    if not r or not in_scope(user, branch_id=r.branch_id, client_id=r.client_id, site_id=r.site_id):
        raise HTTPException(404, "Request not found")
    return r


def _items_ok(db: Session, ids) -> None:
    found = svc.item_names(db, ids)
    if missing := set(ids) - found.keys():
        raise HTTPException(422, f"Unknown item id(s): {sorted(missing)}")


def _apply_estimate(db: Session, r: MaterialRequest, site: Site, qtys: dict[int, int]) -> svc.Estimate:
    est = svc.estimate(
        db,
        client_id=r.client_id,
        project_id=r.project_id,
        site=site,
        duration_days=r.duration_days,
        transport=r.transport_charge,
        qtys=qtys,
    )
    by_item = {ln.item_id: ln for ln in est.lines}
    for ln in r.lines:
        if ln.item_id in by_item:
            ln.rate_per_day, ln.rate_card_id = by_item[ln.item_id].rate_per_day, by_item[ln.item_id].rate_card_id
    r.est_rent, r.est_taxable, r.est_gst, r.est_total = est.rent, est.taxable, est.gst, est.total
    return est


def _stock_http(e: stock.StockError) -> HTTPException:
    return HTTPException(409, {"code": "stock", "message": e.message, "shortages": e.shortages})


def _release(db: Session, r: MaterialRequest, user: User, reason: str) -> None:
    """Return reserved-but-not-dispatched stock to available."""
    lines = []
    for ln in r.lines:
        left = (ln.qty_approved or 0) - ln.qty_dispatched
        if left > 0:
            lines += stock.move(("warehouse", r.warehouse_id), ln.item_id, left, "reserved", "available")
    if lines:
        stock.post(
            db,
            kind="release",
            warehouse_id=r.warehouse_id,
            user_id=user.id,
            source=("request", r.id),
            reason=f"{reason} {r.ref_no}",
            lines=lines,
        )


def _approved_map(r: MaterialRequest, lines: list[ApproveLine]) -> dict[int, int]:
    req = {ln.item_id: ln.qty_requested for ln in r.lines}
    got = {ln.item_id: ln.qty for ln in lines}
    if set(got) != set(req):
        raise HTTPException(422, "Give an approved quantity for every line (0 to leave it out)")
    for k, q in got.items():
        if q > req[k]:
            raise HTTPException(422, "Approved quantity cannot exceed the requested quantity")
    if not any(got.values()):
        raise HTTPException(422, "Approve at least one item, or reject the request")
    return got


def _check_approver(db: Session, user: User, r: MaterialRequest, approved: dict[int, int]) -> svc.Estimate:
    if r.status != "submitted":
        raise HTTPException(400, f"Request is {r.status}")
    if r.created_by == user.id and "owner" not in user.role_codes:
        raise HTTPException(403, "You cannot approve your own request")
    client = db.get(Client, r.client_id)
    if client.credit_status == "hold":
        raise HTTPException(409, "Client is on credit hold. Accounts must release the hold first.")
    site = db.get(Site, r.site_id)
    est = svc.estimate(
        db,
        client_id=r.client_id,
        project_id=r.project_id,
        site=site,
        duration_days=r.duration_days,
        transport=r.transport_charge,
        qtys={k: v for k, v in approved.items() if v},
    )
    limit = svc.approval_limit(user)
    if limit is not None and est.total > limit:
        raise HTTPException(403, f"Value ₹{est.total} is above your approval limit of ₹{limit}")
    avail = svc.availability(db, [k for k, v in approved.items() if v], [r.warehouse_id])
    short = [
        {"item_id": k, "need": v, "available": avail[k].get(r.warehouse_id, 0)}
        for k, v in approved.items()
        if v and avail[k].get(r.warehouse_id, 0) < v
    ]
    if short:
        raise HTTPException(
            409, {"code": "stock", "message": "Not enough available stock to reserve", "shortages": short}
        )
    return est


# ---------- requests ----------


@router.post("/requests/estimate")
def estimate_preview(body: EstimateIn, db: Session = Depends(get_db), user: User = Depends(require("requests.create"))):
    """Price and live stock check for a draft request (nothing saved)."""
    site, proj, cl = _site_chain(db, user, body.site_id)
    _items_ok(db, [ln.item_id for ln in body.lines])
    qtys = {ln.item_id: ln.qty for ln in body.lines}
    est = svc.estimate(
        db,
        client_id=cl.id,
        project_id=proj.id,
        site=site,
        duration_days=body.duration_days,
        transport=body.transport_charge,
        qtys=qtys,
    )
    return {
        **est.as_dict(),
        "availability": _availability_rows(db, qtys, body.warehouse_id),
        "client": {"id": cl.id, "name": cl.name, "credit_status": cl.credit_status},
    }


def _availability_rows(db: Session, qtys: dict[int, int], warehouse_id: int | None) -> list[dict]:
    av = svc.availability(db, list(qtys))
    whs = {w.id: w for w in db.scalars(select(Warehouse))}
    rows = []
    for item_id, need in qtys.items():
        here = av[item_id].get(warehouse_id, 0) if warehouse_id else None
        others = [
            {"warehouse_id": w, "code": whs[w].code, "available": q}
            for w, q in sorted(av[item_id].items(), key=lambda kv: -kv[1])
            if w != warehouse_id
        ]
        rows.append(
            {
                "item_id": item_id,
                "need": need,
                "available": here,
                "short": max(0, need - here) if here is not None else None,
                "elsewhere": others,
            }
        )
    return rows


@router.get("/requests", response_model=list[RequestOut])
def list_requests(
    status: str | None = None,
    site_id: int | None = None,
    client_id: int | None = None,
    pending_my_approval: bool = False,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.view")),
):
    stmt = select(MaterialRequest).order_by(MaterialRequest.id.desc()).limit(limit)
    for kind, col in (
        ("branch", MaterialRequest.branch_id),
        ("client", MaterialRequest.client_id),
        ("site", MaterialRequest.site_id),
    ):
        if (ids := scope_ids(user, kind)) is not None:
            stmt = stmt.where(col.in_(ids))
    if status == "open":
        stmt = stmt.where(MaterialRequest.status.in_(OPEN_STATUSES))
    elif status:
        stmt = stmt.where(MaterialRequest.status == status)
    if site_id:
        stmt = stmt.where(MaterialRequest.site_id == site_id)
    if client_id:
        stmt = stmt.where(MaterialRequest.client_id == client_id)
    if pending_my_approval:
        if "requests.approve" not in user.permission_codes:
            return []
        stmt = stmt.where(MaterialRequest.status == "submitted")
        if "owner" not in user.role_codes:
            stmt = stmt.where(MaterialRequest.created_by != user.id)
    return list(db.scalars(stmt))


@router.post("/requests", response_model=RequestOut, status_code=201)
def create_request(
    body: RequestIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("requests.create"))
):
    site, proj, cl = _site_chain(db, user, body.site_id)
    if not cl.is_active or not proj.is_active:
        raise HTTPException(422, "Client or project is inactive")
    w = _warehouse(db, body.warehouse_id)
    _items_ok(db, [ln.item_id for ln in body.lines])
    r = MaterialRequest(
        ref_no=svc.next_number(db, MaterialRequest, MaterialRequest.ref_no, "REQ"),
        client_id=cl.id,
        project_id=proj.id,
        site_id=site.id,
        branch_id=proj.branch_id,
        warehouse_id=w.id,
        required_on=body.required_on,
        duration_days=body.duration_days,
        transport_charge=body.transport_charge,
        note=body.note,
        created_by=user.id,
        lines=[RequestLine(item_id=ln.item_id, qty_requested=ln.qty) for ln in body.lines],
    )
    db.add(r)
    db.flush()
    _apply_estimate(db, r, site, {ln.item_id: ln.qty for ln in body.lines})
    audit.record(
        db,
        "request.created",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={
            "site_id": site.id,
            "warehouse_id": w.id,
            "total": str(r.est_total),
            "lines": [ln.model_dump() for ln in body.lines],
        },
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


@router.get("/requests/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(require("requests.view"))):
    r = _get(db, user, request_id)
    out = RequestOut.model_validate(r).model_dump()
    qtys = {ln.item_id: ln.qty_requested for ln in r.lines}
    out["availability"] = _availability_rows(db, qtys, r.warehouse_id) if r.status == "submitted" else []
    cl, site = db.get(Client, r.client_id), db.get(Site, r.site_id)
    out["client"] = {"id": cl.id, "code": cl.code, "name": cl.name, "credit_status": cl.credit_status}
    out["site"] = {"id": site.id, "code": site.code, "name": site.name, "state_code": site.state_code}
    out["warehouse"] = {"id": r.warehouse_id, "code": db.get(Warehouse, r.warehouse_id).code}
    limit = svc.approval_limit(user)
    out["can_approve"] = (
        r.status == "submitted"
        and "requests.approve" in user.permission_codes
        and (r.created_by != user.id or "owner" in user.role_codes)
        and (limit is None or r.est_total <= limit)
    )
    out["my_approval_limit"] = limit
    return out


@router.put("/requests/{request_id}", response_model=RequestOut)
def amend_request(
    request_id: int,
    body: RequestIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.create")),
):
    """Amendment: allowed until the first dispatch. Voids any approval (stock un-reserved) -> reapproval."""
    r = _get(db, user, request_id, lock=True)
    if r.status not in ("submitted", "approved"):
        raise HTTPException(400, f"A {r.status} request cannot be amended")
    if body.site_id != r.site_id:
        raise HTTPException(422, "Site cannot change; cancel and raise a new request")
    site = db.get(Site, r.site_id)
    w = _warehouse(db, body.warehouse_id)
    _items_ok(db, [ln.item_id for ln in body.lines])
    was = r.status
    if was == "approved":
        try:
            _release(db, r, user, "Amended")
        except stock.StockError as e:
            db.rollback()
            raise _stock_http(e) from None
    r.lines.clear()
    db.flush()
    r.lines.extend(RequestLine(item_id=ln.item_id, qty_requested=ln.qty) for ln in body.lines)
    r.warehouse_id, r.required_on, r.duration_days = w.id, body.required_on, body.duration_days
    r.transport_charge, r.note = body.transport_charge, body.note
    r.status, r.version = "submitted", r.version + 1
    r.approved_by = r.approved_at = r.approved_version = None
    db.flush()
    _apply_estimate(db, r, site, {ln.item_id: ln.qty for ln in body.lines})
    audit.record(
        db,
        "request.amended",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={
            "version": r.version,
            "was": was,
            "total": str(r.est_total),
            "lines": [ln.model_dump() for ln in body.lines],
        },
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


@router.post("/requests/{request_id}/approval-otp")
def approval_otp(
    request_id: int,
    body: OtpRequestIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.approve")),
):
    """Step 1 of approval: checks everything, then sends an OTP bound to these exact quantities."""
    r = _get(db, user, request_id)
    approved = _approved_map(r, body.lines)
    est = _check_approver(db, user, r, approved)
    try:
        ch = otp.issue(db, user, OTP_PURPOSE, svc.approval_ref(r, approved))
    except otp.OtpError as e:
        raise HTTPException(429, {"code": e.code, "message": e.message}) from None
    audit.record(
        db,
        "request.approval_otp_sent",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={"version": r.version, "total": str(est.total)},
        ip=client_ip(request),
    )
    db.commit()
    sent_to = mask(user.email if ch.channel == "email" else user.phone)
    return {
        "challenge_id": ch.id,
        "channel": ch.channel,
        "expires_at": ch.expires_at,
        "sent_to": sent_to,
        "estimate": est.as_dict(),
    }


@router.post("/requests/{request_id}/approve", response_model=RequestOut)
def approve(
    request_id: int,
    body: ApproveIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.approve")),
):
    """Step 2: verify the OTP, reserve the stock and mark approved."""
    r = _get(db, user, request_id, lock=True)
    approved = _approved_map(r, body.lines)
    est = _check_approver(db, user, r, approved)
    try:
        otp.verify(db, body.challenge_id, body.code, purpose=OTP_PURPOSE, transaction_ref=svc.approval_ref(r, approved))
    except otp.OtpError as e:
        audit.record(
            db,
            "request.approval_otp_failed",
            user_id=user.id,
            entity="request",
            entity_id=r.ref_no,
            data={"reason": e.code},
            ip=client_ip(request),
        )
        db.commit()  # keep the attempt count
        raise HTTPException(400, {"code": e.code, "message": e.message}) from None
    lines = []
    for ln in r.lines:
        ln.qty_approved = approved[ln.item_id]
        if ln.qty_approved:
            lines += stock.move(("warehouse", r.warehouse_id), ln.item_id, ln.qty_approved, "available", "reserved")
    try:
        stock.post(
            db,
            kind="reserve",
            warehouse_id=r.warehouse_id,
            user_id=user.id,
            source=("request", r.id),
            reason=f"Approved {r.ref_no}",
            lines=lines,
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    r.est_rent, r.est_taxable, r.est_gst, r.est_total = est.rent, est.taxable, est.gst, est.total
    r.status, r.approved_by, r.approved_at = "approved", user.id, datetime.now(UTC)
    r.approved_version, r.decision_note = r.version, body.note
    partial = any(approved[ln.item_id] < ln.qty_requested for ln in r.lines)
    audit.record(
        db,
        "request.approved",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={"version": r.version, "total": str(est.total), "partial": partial, "approved": approved, "otp": True},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


@router.post("/requests/{request_id}/reject", response_model=RequestOut)
def reject(
    request_id: int,
    body: ReasonIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.approve")),
):
    r = _get(db, user, request_id, lock=True)
    if r.status != "submitted":
        raise HTTPException(400, f"Request is {r.status}")
    r.status, r.decision_note, r.closed_at = "rejected", body.reason, datetime.now(UTC)
    audit.record(
        db,
        "request.rejected",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={"reason": body.reason},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


@router.post("/requests/{request_id}/cancel", response_model=RequestOut)
def cancel(
    request_id: int,
    body: ReasonIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cancel before any dispatch (raiser or approver). Reserved stock goes back to available."""
    r = _get(db, user, request_id, lock=True)
    perms = user.permission_codes
    if not ("requests.approve" in perms or (r.created_by == user.id and "requests.create" in perms)):
        raise HTTPException(403, "Only the person who raised it or an approver can cancel")
    if r.status not in ("submitted", "approved"):
        raise HTTPException(400, f"A {r.status} request cannot be cancelled; close it instead")
    try:
        if r.status == "approved":
            _release(db, r, user, "Cancelled")
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    r.status, r.decision_note, r.closed_at = "cancelled", body.reason, datetime.now(UTC)
    audit.record(
        db,
        "request.cancelled",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={"reason": body.reason},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


@router.post("/requests/{request_id}/close", response_model=RequestOut)
def close(
    request_id: int,
    body: ReasonIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Close a part-dispatched request: the rest of the reservation is released."""
    if not user.permission_codes & {"dispatch.manage", "requests.approve"}:
        raise HTTPException(403, "Missing permission: dispatch.manage")
    r = _get(db, user, request_id, lock=True)
    if r.status != "part_dispatched":
        raise HTTPException(400, "Only a part-dispatched request can be closed")
    try:
        _release(db, r, user, "Closed")
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    r.status, r.decision_note, r.closed_at = "closed", body.reason, datetime.now(UTC)
    audit.record(
        db,
        "request.closed",
        user_id=user.id,
        entity="request",
        entity_id=r.ref_no,
        data={"reason": body.reason},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(r)
    return r


# ---------- dispatch ----------


@router.post("/requests/{request_id}/dispatches", response_model=DispatchOut, status_code=201)
def dispatch(
    request_id: int,
    body: DispatchIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("dispatch.manage")),
    idempotency_key: str | None = Header(default=None),
):
    """Dispatch confirms the actual quantities leaving the yard (can be partial)."""
    if (done := stock.replay(db, idempotency_key)) and done.source_type == "dispatch":
        return db.get(Dispatch, done.source_id)
    r = _get(db, user, request_id, lock=True)
    wh_scope = scope_ids(user, "warehouse")
    if wh_scope is not None and r.warehouse_id not in wh_scope:
        raise HTTPException(403, "This request ships from a warehouse outside your scope")
    if r.status not in ("approved", "part_dispatched"):
        raise HTTPException(400, f"Request is {r.status}; only approved requests can be dispatched")
    by_item = {ln.item_id: ln for ln in r.lines}
    for ln in body.lines:
        rl = by_item.get(ln.item_id)
        if not rl:
            raise HTTPException(422, f"Item {ln.item_id} is not on this request")
        left = (rl.qty_approved or 0) - rl.qty_dispatched
        if ln.qty > left:
            raise HTTPException(422, f"Item {ln.item_id}: only {left} approved and not yet dispatched")
    branch = db.get(Branch, r.branch_id)
    prefix = f"DC/{branch.code}/{svc.fin_year(svc.today_ist())}"
    d = Dispatch(
        challan_no=svc.next_number(db, Dispatch, Dispatch.challan_no, prefix, width=5, sep="/"),
        request_id=r.id,
        warehouse_id=r.warehouse_id,
        site_id=r.site_id,
        vehicle_no=body.vehicle_no,
        driver_name=body.driver_name,
        driver_phone=body.driver_phone,
        note=body.note,
        dispatched_by=user.id,
        lines=[DispatchLine(item_id=ln.item_id, qty=ln.qty) for ln in body.lines],
    )
    db.add(d)
    db.flush()
    lines = []
    for ln in body.lines:
        by_item[ln.item_id].qty_dispatched += ln.qty
        lines += stock.move(
            ("warehouse", r.warehouse_id), ln.item_id, ln.qty, "reserved", "in_transit", to_location=("challan", d.id)
        )
    try:
        stock.post(
            db,
            kind="dispatch",
            warehouse_id=r.warehouse_id,
            user_id=user.id,
            source=("dispatch", d.id),
            reason=f"{d.challan_no} for {r.ref_no}",
            idempotency_key=idempotency_key,
            lines=lines,
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    full = all(ln.qty_dispatched >= (ln.qty_approved or 0) for ln in r.lines)
    r.status = "dispatched" if full else "part_dispatched"
    audit.record(
        db,
        "dispatch.created",
        user_id=user.id,
        entity="dispatch",
        entity_id=d.challan_no,
        data={"request": r.ref_no, "vehicle_no": body.vehicle_no, "lines": [ln.model_dump() for ln in body.lines]},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(d)
    return d


def _dispatch_scoped(db: Session, user: User, dispatch_id: int, lock: bool = False) -> Dispatch:
    d = db.get(Dispatch, dispatch_id, with_for_update=lock)
    if not d:
        raise HTTPException(404, "Dispatch not found")
    _get(db, user, d.request_id)
    return d


@router.get("/dispatches", response_model=list[DispatchOut])
def list_dispatches(
    status: str | None = None,
    site_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require("requests.view")),
):
    stmt = select(Dispatch).join(MaterialRequest).order_by(Dispatch.id.desc()).limit(200)
    for kind, col in (
        ("branch", MaterialRequest.branch_id),
        ("client", MaterialRequest.client_id),
        ("site", MaterialRequest.site_id),
    ):
        if (ids := scope_ids(user, kind)) is not None:
            stmt = stmt.where(col.in_(ids))
    if status:
        stmt = stmt.where(Dispatch.status == status)
    if site_id:
        stmt = stmt.where(Dispatch.site_id == site_id)
    return list(db.scalars(stmt))


@router.get("/dispatches/{dispatch_id}/challan.pdf")
def challan_pdf(dispatch_id: int, db: Session = Depends(get_db), user: User = Depends(require("requests.view"))):
    d = _dispatch_scoped(db, user, dispatch_id)
    pdf = challan.render(db, d)
    name = d.challan_no.replace("/", "-")
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'}
    )


@router.post("/dispatches/{dispatch_id}/receive", response_model=DispatchOut)
def receive(
    dispatch_id: int,
    body: ReceiveIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Site acknowledgement. Received pieces are at site (rent runs from here); any shortfall is
    marked missing at the dispatching warehouse."""
    perms = user.permission_codes
    if not perms & {"dispatch.manage", "requests.create"}:
        raise HTTPException(403, "Missing permission: dispatch.manage or requests.create")
    d = _dispatch_scoped(db, user, dispatch_id, lock=True)
    if d.status != "in_transit":
        raise HTTPException(400, "This challan is already acknowledged")
    got = {ln.item_id: ln.received for ln in body.lines}
    if extra := set(got) - {ln.item_id for ln in d.lines}:
        raise HTTPException(422, f"Item(s) not on this challan: {sorted(extra)}")
    lines = []
    for dl in d.lines:
        rec = got.get(dl.item_id, 0)
        if rec > dl.qty:
            raise HTTPException(422, f"Item {dl.item_id}: received is more than dispatched ({dl.qty})")
        dl.qty_received, dl.qty_short = rec, dl.qty - rec
        if rec:
            lines += stock.move(("challan", d.id), dl.item_id, rec, "in_transit", "at_site", ("site", d.site_id))
        if dl.qty_short:
            lines += stock.move(
                ("challan", d.id), dl.item_id, dl.qty_short, "in_transit", "missing", ("warehouse", d.warehouse_id)
            )
    try:
        stock.post(
            db,
            kind="site_receipt",
            warehouse_id=d.warehouse_id,
            user_id=user.id,
            source=("dispatch", d.id),
            reason=f"Site receipt {d.challan_no}",
            note=body.note,
            lines=lines,
        )
    except stock.StockError as e:
        db.rollback()
        raise _stock_http(e) from None
    d.status, d.received_by, d.received_at = "received", user.id, datetime.now(UTC)
    d.receiver_name, d.receipt_note = body.receiver_name, body.note
    short = sum(dl.qty_short for dl in d.lines)
    audit.record(
        db,
        "dispatch.received",
        user_id=user.id,
        entity="dispatch",
        entity_id=d.challan_no,
        data={"receiver": body.receiver_name, "short": short},
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(d)
    return d
