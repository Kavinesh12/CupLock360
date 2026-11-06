from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import client_ip, require
from app.core.security import hash_password
from app.models import Permission, Role, User, UserScope, user_roles
from app.modules.auth.service import revoke_all_sessions
from app.modules.users.schemas import (
    PermissionOut,
    RoleOut,
    RolePermissionsUpdate,
    ScopeIn,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import audit

router = APIRouter(tags=["users & roles"])

PRIVILEGED_ROLES = {"owner", "sysadmin"}


def _out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, full_name=u.full_name, phone=u.phone, email=u.email,
        is_active=u.is_active, roles=u.role_codes, approval_limit=u.approval_limit,
        scopes=[ScopeIn(type=s.scope_type, id=s.scope_id) for s in u.scopes],
    )


def _resolve_roles(db: Session, codes: list[str], actor: User) -> list[Role]:
    roles = list(db.scalars(select(Role).where(Role.code.in_(codes))))
    unknown = set(codes) - {r.code for r in roles}
    if unknown:
        raise HTTPException(422, f"Unknown role(s): {', '.join(sorted(unknown))}")
    if PRIVILEGED_ROLES & set(codes) and "owner" not in actor.role_codes:
        raise HTTPException(403, "Only the business owner can grant Owner or System Administrator roles")
    return roles


def _snapshot(u: User) -> dict:
    return {"full_name": u.full_name, "phone": u.phone, "email": u.email, "is_active": u.is_active,
            "roles": u.role_codes, "approval_limit": u.approval_limit,
            "scopes": [[s.scope_type, s.scope_id] for s in u.scopes]}


@router.get("/users", response_model=list[UserOut])
def list_users(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    stmt = select(User).order_by(User.full_name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.full_name).like(like) | User.username.like(like) | User.phone.like(like))
    return [_out(u) for u in db.scalars(stmt)]


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require("users.view"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return _out(u)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(require("users.manage"))):
    u = User(username=body.username, full_name=body.full_name, phone=body.phone,
             email=body.email.lower() if body.email else None, password_hash=hash_password(body.password),
             approval_limit=body.approval_limit)
    u.roles = _resolve_roles(db, body.roles, actor)
    u.scopes = [UserScope(scope_type=s.type, scope_id=s.id) for s in body.scopes]
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username, phone or email already in use") from None
    audit.record(db, "user.created", user_id=actor.id, entity="user", entity_id=u.id,
                 data=_snapshot(u), ip=client_ip(request))
    db.commit()
    return _out(u)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(require("users.manage"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if PRIVILEGED_ROLES & set(u.role_codes) and "owner" not in actor.role_codes:
        raise HTTPException(403, "Only the business owner can edit this user")
    before = _snapshot(u)
    changes = body.model_dump(exclude_unset=True)
    if u.id == actor.id and (changes.get("is_active") is False or
                             ("roles" in changes and "owner" in u.role_codes and "owner" not in changes["roles"])):
        raise HTTPException(400, "You cannot deactivate yourself or remove your own Owner role")

    revoke = False
    for field in ("full_name", "phone", "approval_limit"):
        if field in changes:
            setattr(u, field, changes[field])
    if "email" in changes:
        u.email = changes["email"].lower() if changes["email"] else None
    if changes.get("password"):
        u.password_hash = hash_password(changes["password"])
        revoke = True
    if "roles" in changes:
        u.roles = _resolve_roles(db, changes["roles"], actor)
        revoke = True
    if "scopes" in changes:
        u.scopes = [UserScope(scope_type=s["type"], scope_id=s["id"]) for s in changes["scopes"]]
        revoke = True
    if "is_active" in changes:
        u.is_active = changes["is_active"]
        revoke = revoke or not u.is_active
    if revoke:
        revoke_all_sessions(db, u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Phone or email already in use") from None
    audit.record(db, "user.updated", user_id=actor.id, entity="user", entity_id=u.id,
                 data={"before": before, "after": _snapshot(u), "sessions_revoked": revoke},
                 ip=client_ip(request))
    db.commit()
    return _out(u)


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_sessions(user_id: int, request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(require("users.manage"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    revoke_all_sessions(db, u)
    audit.record(db, "user.sessions_revoked", user_id=actor.id, entity="user", entity_id=u.id,
                 ip=client_ip(request))
    db.commit()


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), _: User = Depends(require("roles.view"))):
    return list(db.scalars(select(Permission).order_by(Permission.module, Permission.code)))


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _: User = Depends(require("roles.view"))):
    counts = dict(db.execute(select(user_roles.c.role_id, func.count()).group_by(user_roles.c.role_id)).all())
    return [
        RoleOut(id=r.id, code=r.code, name=r.name, description=r.description, is_system=r.is_system,
                permissions=sorted(p.code for p in r.permissions), user_count=counts.get(r.id, 0))
        for r in db.scalars(select(Role).order_by(Role.id))
    ]


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(role_id: int, body: RolePermissionsUpdate, request: Request,
                         db: Session = Depends(get_db), actor: User = Depends(require("roles.manage"))):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(404, "Role not found")
    if r.code == "owner":
        raise HTTPException(400, "The Owner role always has every permission")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    unknown = set(body.permissions) - {p.code for p in perms}
    if unknown:
        raise HTTPException(422, f"Unknown permission(s): {', '.join(sorted(unknown))}")
    before = sorted(p.code for p in r.permissions)
    r.permissions = perms
    audit.record(db, "role.permissions_changed", user_id=actor.id, entity="role", entity_id=r.id,
                 data={"before": before, "after": sorted(body.permissions)}, ip=client_ip(request))
    db.commit()
    count = db.scalar(select(func.count()).select_from(user_roles).where(user_roles.c.role_id == r.id))
    return RoleOut(id=r.id, code=r.code, name=r.name, description=r.description, is_system=r.is_system,
                   permissions=sorted(p.code for p in r.permissions), user_count=count or 0)
