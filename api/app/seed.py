"""Idempotent seed: permissions, the 12 default roles, and the bootstrap owner account.

Run with:  python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.rbac import PERMISSIONS, ROLES
from app.core.security import hash_password
from app.models import Permission, Role, User
from app.services import audit


def seed(db: Session) -> None:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, (module, desc) in PERMISSIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, module=module, description=desc)
            db.add(perms[code])
        else:
            perms[code].module, perms[code].description = module, desc
    db.flush()

    roles = {r.code: r for r in db.scalars(select(Role))}
    for code, (name, desc, codes) in ROLES.items():
        role = roles.get(code)
        if role is None:
            role = Role(code=code, name=name, description=desc, is_system=True)
            role.permissions = [perms[c] for c in sorted(codes)]
            db.add(role)
            roles[code] = role
        elif code == "owner":
            role.permissions = [perms[c] for c in sorted(codes)]  # owner always gets new permissions
    db.flush()

    s = get_settings()
    if not db.scalar(select(User).where(User.username == s.owner_username)):
        owner = User(username=s.owner_username, full_name="Business Owner", phone=s.owner_phone,
                     email=s.owner_email, password_hash=hash_password(s.owner_password))
        owner.roles = [roles["owner"]]
        db.add(owner)
        db.flush()
        audit.record(db, "system.owner_created", entity="user", entity_id=owner.id)
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("Seed complete.")
