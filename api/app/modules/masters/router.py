from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, in_scope, require, scope_ids
from app.core.gst import STATES, state_from_gstin
from app.models import Branch, Client, Project, Site, User
from app.modules.masters.schemas import (
    CREDIT_FIELDS,
    ClientCreate,
    ClientDetail,
    ClientOut,
    ClientUpdate,
    ProjectIn,
    ProjectOut,
    SiteIn,
    SiteListOut,
    SiteOut,
)
from app.services import audit

router = APIRouter(tags=["clients, projects & sites"])


def _apply_state(obj, state_code: str | None, gstin: str | None = None) -> None:
    if gstin:
        state_code, _ = state_from_gstin(gstin)
    if state_code:
        obj.state_code = state_code
        obj.state = STATES[state_code]


def _get_client(db: Session, user: User, client_id: int) -> Client:
    c = db.get(Client, client_id)
    if not c or not in_scope(user, branch_id=c.branch_id, client_id=c.id):
        raise HTTPException(404, "Client not found")
    return c


def _check_branch(db: Session, user: User, branch_id: int) -> None:
    if not db.get(Branch, branch_id):
        raise HTTPException(422, "Branch not found")
    if not in_scope(user, branch_id=branch_id):
        raise HTTPException(403, "Branch is outside your scope")


def _flush(db: Session, what: str) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"{what} already exists (duplicate code or GSTIN)") from None


def client_query(user: User):
    stmt = select(Client)
    if (b := scope_ids(user, "branch")) is not None:
        stmt = stmt.where(Client.branch_id.in_(b))
    if (c := scope_ids(user, "client")) is not None:
        stmt = stmt.where(Client.id.in_(c))
    return stmt


@router.get("/clients", response_model=list[ClientOut])
def list_clients(q: str | None = None, branch_id: int | None = None, active: bool | None = None,
                 db: Session = Depends(get_db), user: User = Depends(require("clients.view"))):
    stmt = client_query(user).order_by(Client.name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Client.name).like(like), func.lower(Client.code).like(like),
                              Client.gstin.like(f"%{q.upper()}%"), Client.phone.like(like)))
    if branch_id:
        stmt = stmt.where(Client.branch_id == branch_id)
    if active is not None:
        stmt = stmt.where(Client.is_active == active)
    return list(db.scalars(stmt.limit(500)))


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientCreate, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("clients.manage"))):
    _check_branch(db, user, body.branch_id)
    data = body.model_dump()
    if "clients.credit" not in user.permission_codes:
        # Without credit authority a new client starts with default terms and pending credit.
        for f in CREDIT_FIELDS:
            data.pop(f)
    c = Client(**{k: v for k, v in data.items() if k != "state_code"}, code="TMP")
    _apply_state(c, body.state_code, body.gstin)
    db.add(c)
    _flush(db, "Client")
    c.code = f"CL-{c.id:04d}"
    audit.record(db, "client.created", user_id=user.id, entity="client", entity_id=c.id,
                 data=data, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return c


@router.get("/clients/{client_id}", response_model=ClientDetail)
def get_client(client_id: int, db: Session = Depends(get_db), user: User = Depends(require("clients.view"))):
    c = _get_client(db, user, client_id)
    out = ClientDetail.model_validate(c)
    allowed_sites = scope_ids(user, "site")
    if allowed_sites is not None:
        for p in out.projects:
            p.sites = [s for s in p.sites if s.id in allowed_sites]
    return out


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientUpdate, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("clients.manage"))):
    c = _get_client(db, user, client_id)
    changes = body.model_dump(exclude_unset=True)
    if CREDIT_FIELDS & changes.keys() and "clients.credit" not in user.permission_codes:
        raise HTTPException(403, "Missing permission: clients.credit")
    if "branch_id" in changes:
        _check_branch(db, user, changes["branch_id"])
    before = ClientOut.model_validate(c).model_dump(mode="json")
    for k, v in changes.items():
        if k != "state_code":
            setattr(c, k, v)
    _apply_state(c, changes.get("state_code"), changes.get("gstin"))
    _flush(db, "Client")
    after = ClientOut.model_validate(c).model_dump(mode="json")
    audit.record(db, "client.updated", user_id=user.id, entity="client", entity_id=c.id,
                 data={"before": {k: before[k] for k in changes if k in before},
                       "after": {k: after[k] for k in changes if k in after}}, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return c


@router.post("/clients/{client_id}/projects", response_model=ProjectOut, status_code=201)
def create_project(client_id: int, body: ProjectIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("clients.manage"))):
    c = _get_client(db, user, client_id)
    branch_id = body.branch_id or c.branch_id
    _check_branch(db, user, branch_id)
    n = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == c.id)) + 1
    p = Project(client_id=c.id, code=f"P-{c.id:04d}-{n:02d}", name=body.name, branch_id=branch_id,
                start_date=body.start_date, is_active=body.is_active)
    db.add(p)
    _flush(db, "Project")
    audit.record(db, "project.created", user_id=user.id, entity="project", entity_id=p.id,
                 data={"client_id": c.id, "name": p.name}, ip=client_ip(request))
    db.commit()
    return p


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("clients.manage"))):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    _get_client(db, user, p.client_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("branch_id"):
        _check_branch(db, user, changes["branch_id"])
    for k, v in changes.items():
        if v is not None or k == "start_date":
            setattr(p, k, v)
    audit.record(db, "project.updated", user_id=user.id, entity="project", entity_id=p.id,
                 data=body.model_dump(mode="json", exclude_unset=True), ip=client_ip(request))
    db.commit()
    return p


@router.post("/projects/{project_id}/sites", response_model=SiteOut, status_code=201)
def create_site(project_id: int, body: SiteIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("clients.manage"))):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    _get_client(db, user, p.client_id)
    if body.manager_user_id and not db.get(User, body.manager_user_id):
        raise HTTPException(422, "Site manager user not found")
    s = Site(project_id=p.id, code="TMP", **body.model_dump(exclude={"state_code"}))
    _apply_state(s, body.state_code)
    db.add(s)
    _flush(db, "Site")
    s.code = f"S-{s.id:04d}"
    audit.record(db, "site.created", user_id=user.id, entity="site", entity_id=s.id,
                 data={"project_id": p.id, **body.model_dump(mode="json")}, ip=client_ip(request))
    db.commit()
    return s


@router.patch("/sites/{site_id}", response_model=SiteOut)
def update_site(site_id: int, body: SiteIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("clients.manage"))):
    s = db.get(Site, site_id)
    if not s:
        raise HTTPException(404, "Site not found")
    _get_client(db, user, s.project.client_id)
    for k, v in body.model_dump(exclude={"state_code"}).items():
        setattr(s, k, v)
    _apply_state(s, body.state_code)
    audit.record(db, "site.updated", user_id=user.id, entity="site", entity_id=s.id,
                 data=body.model_dump(mode="json"), ip=client_ip(request))
    db.commit()
    return s


@router.get("/sites", response_model=list[SiteListOut])
def list_sites(client_id: int | None = None, project_id: int | None = None, q: str | None = None,
               db: Session = Depends(get_db), user: User = Depends(require("clients.view"))):
    stmt = (select(Site, Project, Client).join(Project, Site.project_id == Project.id)
            .join(Client, Project.client_id == Client.id).order_by(Client.name, Site.name))
    if (b := scope_ids(user, "branch")) is not None:
        stmt = stmt.where(Project.branch_id.in_(b))
    if (c := scope_ids(user, "client")) is not None:
        stmt = stmt.where(Client.id.in_(c))
    if (si := scope_ids(user, "site")) is not None:
        stmt = stmt.where(Site.id.in_(si))
    if client_id:
        stmt = stmt.where(Client.id == client_id)
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Site.name).like(like), func.lower(Client.name).like(like)))
    return [SiteListOut(**SiteOut.model_validate(s).model_dump(), project_name=p.name, client_id=c.id,
                        client_name=c.name) for s, p, c in db.execute(stmt.limit(500))]
