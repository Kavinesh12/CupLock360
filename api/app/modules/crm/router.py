from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, in_scope, require, scope_ids
from app.models import Branch, Client, FollowUp, Lead, Project, Site, User
from app.modules.masters.schemas import ClientOut, ProjectOut, SiteOut
from app.services import audit

router = APIRouter(prefix="/leads", tags=["leads"])

OPEN = ("new", "contacted", "quoted")
IST = timedelta(hours=5, minutes=30)
Status = Literal["new", "contacted", "quoted", "lost"]
Channel = Literal["call", "visit", "whatsapp", "email", "meeting"]


class LeadIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str | None = None
    phone: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    city: str | None = None
    source: str | None = None
    requirement: str | None = None
    est_value: Decimal | None = Field(default=None, ge=0)
    branch_id: int
    assigned_to: int | None = None
    next_follow_up_at: datetime | None = None


class LeadUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=2, max_length=200)
    contact_name: str | None = None
    phone: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    city: str | None = None
    source: str | None = None
    requirement: str | None = None
    est_value: Decimal | None = Field(default=None, ge=0)
    assigned_to: int | None = None
    next_follow_up_at: datetime | None = None
    status: Status | None = None
    lost_reason: str | None = None


class FollowUpIn(BaseModel):
    channel: Channel = "call"
    note: str = Field(min_length=1, max_length=2000)
    next_follow_up_at: datetime | None = None
    status: Status | None = None
    lost_reason: str | None = None


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    at: datetime
    by_user_id: int
    channel: str
    note: str
    next_follow_up_at: datetime | None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    city: str | None
    source: str | None
    requirement: str | None
    est_value: Decimal | None
    status: str
    lost_reason: str | None
    branch_id: int
    assigned_to: int | None
    created_by: int
    next_follow_up_at: datetime | None
    converted_client_id: int | None
    created_at: datetime


class LeadDetail(LeadOut):
    follow_ups: list[FollowUpOut]


class ConvertIn(BaseModel):
    existing_client_id: int | None = None
    client_name: str | None = None  # defaults to the lead's company name
    gstin: str | None = None
    billing_address: str | None = None
    project_name: str = Field(min_length=1, max_length=200)
    site_name: str = Field(min_length=1, max_length=200)
    site_address: str | None = None
    site_city: str | None = None


class ConvertOut(BaseModel):
    lead: LeadOut
    client: ClientOut
    project: ProjectOut
    site: SiteOut


def _visible(user: User):
    stmt = select(Lead)
    if (b := scope_ids(user, "branch")) is not None:
        stmt = stmt.where(Lead.branch_id.in_(b))
    if "leads.view_all" not in user.permission_codes:
        stmt = stmt.where(or_(Lead.assigned_to == user.id, Lead.created_by == user.id))
    return stmt


def _get(db: Session, user: User, lead_id: int) -> Lead:
    lead = db.scalar(_visible(user).where(Lead.id == lead_id))
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


def _check_assignee(db: Session, user_id: int | None) -> None:
    if user_id is not None:
        u = db.get(User, user_id)
        if not u or not u.is_active:
            raise HTTPException(422, "Assigned user not found")


def _end_of_today_utc() -> datetime:
    now_ist = datetime.now(UTC) + IST
    return datetime.combine(now_ist.date(), time.max, tzinfo=UTC) - IST


@router.get("", response_model=list[LeadOut])
def list_leads(status: str | None = None, q: str | None = None, due: bool = False, mine: bool = False,
               db: Session = Depends(get_db), user: User = Depends(require("leads.view"))):
    """`status=open` lists new, contacted and quoted leads.

    `due=true` lists open leads with a follow-up due by the end of today (IST).
    """
    stmt = _visible(user).order_by(Lead.next_follow_up_at.asc().nulls_last(), Lead.id.desc())
    if status == "open":
        stmt = stmt.where(Lead.status.in_(OPEN))
    elif status:
        stmt = stmt.where(Lead.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Lead.company_name).like(like), func.lower(Lead.contact_name).like(like),
                              Lead.phone.like(like)))
    if due:
        stmt = stmt.where(Lead.status.in_(OPEN), Lead.next_follow_up_at <= _end_of_today_utc())
    if mine:
        stmt = stmt.where(Lead.assigned_to == user.id)
    return list(db.scalars(stmt.limit(500)))


@router.post("", response_model=LeadOut, status_code=201)
def create_lead(body: LeadIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("leads.manage"))):
    if not db.get(Branch, body.branch_id):
        raise HTTPException(422, "Branch not found")
    if not in_scope(user, branch_id=body.branch_id):
        raise HTTPException(403, "Branch is outside your scope")
    _check_assignee(db, body.assigned_to)
    lead = Lead(**body.model_dump(), created_by=user.id)
    lead.assigned_to = body.assigned_to or user.id
    db.add(lead)
    db.flush()
    audit.record(db, "lead.created", user_id=user.id, entity="lead", entity_id=lead.id,
                 data=body.model_dump(mode="json"), ip=client_ip(request))
    db.commit()
    return lead


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(require("leads.view"))):
    return _get(db, user, lead_id)


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, body: LeadUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("leads.manage"))):
    lead = _get(db, user, lead_id)
    if lead.status == "won":
        raise HTTPException(400, "This lead is already converted to a client")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "lost" and not (changes.get("lost_reason") or lead.lost_reason):
        raise HTTPException(422, "Give a reason when marking a lead lost")
    if "assigned_to" in changes:
        _check_assignee(db, changes["assigned_to"])
    for k, v in changes.items():
        setattr(lead, k, v)
    audit.record(db, "lead.updated", user_id=user.id, entity="lead", entity_id=lead.id,
                 data=body.model_dump(mode="json", exclude_unset=True), ip=client_ip(request))
    db.commit()
    return lead


@router.post("/{lead_id}/follow-ups", response_model=LeadDetail, status_code=201)
def add_follow_up(lead_id: int, body: FollowUpIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("leads.manage"))):
    lead = _get(db, user, lead_id)
    if lead.status in ("won", "lost") and body.status is None:
        raise HTTPException(400, f"Lead is {lead.status}; reopen it by setting a status")
    if body.status == "lost" and not body.lost_reason:
        raise HTTPException(422, "Give a reason when marking a lead lost")
    if lead.status == "won":
        raise HTTPException(400, "This lead is already converted to a client")
    db.add(FollowUp(lead_id=lead.id, at=datetime.now(UTC), by_user_id=user.id, channel=body.channel,
                    note=body.note, next_follow_up_at=body.next_follow_up_at))
    lead.next_follow_up_at = body.next_follow_up_at
    if body.status:
        lead.status = body.status
        if body.status == "lost":
            lead.lost_reason = body.lost_reason
    elif lead.status == "new":
        lead.status = "contacted"
    audit.record(db, "lead.follow_up", user_id=user.id, entity="lead", entity_id=lead.id,
                 data=body.model_dump(mode="json"), ip=client_ip(request))
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/convert", response_model=ConvertOut, status_code=201)
def convert_lead(lead_id: int, body: ConvertIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require("leads.manage", "clients.manage"))):
    """Turn a lead into a client (new or existing) with a project and a first site, in one step."""
    from app.modules.masters.router import _apply_state
    from app.modules.masters.schemas import ClientBase

    lead = _get(db, user, lead_id)
    if lead.status in ("won", "lost"):
        raise HTTPException(400, f"Lead is already {lead.status}")
    if body.existing_client_id:
        client = db.get(Client, body.existing_client_id)
        if not client or not in_scope(user, branch_id=client.branch_id, client_id=client.id):
            raise HTTPException(422, "Client not found")
    else:
        gstin = ClientBase.check_gstin(body.gstin)
        if gstin and db.scalar(select(Client.id).where(Client.gstin == gstin)):
            raise HTTPException(409, "A client with this GSTIN already exists; convert into that client instead")
        client = Client(code="TMP", name=body.client_name or lead.company_name, branch_id=lead.branch_id,
                        gstin=gstin, billing_address=body.billing_address, contact_name=lead.contact_name,
                        phone=lead.phone, email=lead.email)
        _apply_state(client, "33", gstin)
        db.add(client)
        db.flush()
        client.code = f"CL-{client.id:04d}"
    n = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == client.id)) + 1
    project = Project(client_id=client.id, code=f"P-{client.id:04d}-{n:02d}", name=body.project_name,
                      branch_id=lead.branch_id)
    db.add(project)
    db.flush()
    site = Site(project_id=project.id, code="TMP", name=body.site_name, address=body.site_address,
                city=body.site_city or lead.city)
    _apply_state(site, "33")
    db.add(site)
    db.flush()
    site.code = f"S-{site.id:04d}"
    lead.status = "won"
    lead.converted_client_id = client.id
    lead.next_follow_up_at = None
    audit.record(db, "lead.converted", user_id=user.id, entity="lead", entity_id=lead.id,
                 data={"client_id": client.id, "project_id": project.id, "site_id": site.id,
                       "new_client": not body.existing_client_id}, ip=client_ip(request))
    db.commit()
    db.refresh(project)
    return ConvertOut(lead=LeadOut.model_validate(lead), client=ClientOut.model_validate(client),
                      project=ProjectOut.model_validate(project), site=SiteOut.model_validate(site))
