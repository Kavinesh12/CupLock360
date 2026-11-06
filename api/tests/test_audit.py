import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal
from tests.conftest import auth, login

API = "/api/v1"


def test_login_writes_audit_rows_and_chain_verifies(client):
    owner = login(client)
    rows = client.get(f"{API}/audit", headers=auth(owner)).json()
    actions = [r["action"] for r in rows]
    assert "auth.login" in actions
    assert "auth.otp_sent" in actions
    assert client.get(f"{API}/audit/verify", headers=auth(owner)).json() == {"ok": True, "first_broken_id": None}


def test_audit_log_rejects_update_and_delete():
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE audit_log SET action = 'x'"))
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(text("DELETE FROM audit_log"))
        db.rollback()


def test_tampering_is_detected(client):
    owner = login(client)
    with SessionLocal() as db:
        db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update_delete"))
        db.execute(text("UPDATE audit_log SET action = 'tampered' WHERE id = 2"))
        db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update_delete"))
        db.commit()
    assert client.get(f"{API}/audit/verify", headers=auth(owner)).json() == {"ok": False, "first_broken_id": 2}


def test_storekeeper_cannot_read_audit(client):
    owner = login(client)
    client.post(f"{API}/users", json={"username": "store9", "full_name": "SK", "password": "Passw0rd!x",
                                      "roles": ["storekeeper"]}, headers=auth(owner))
    sk = login(client, "store9", "Passw0rd!x")
    assert client.get(f"{API}/audit", headers=auth(sk)).status_code == 403
