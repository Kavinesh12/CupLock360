from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.models import OtpChallenge
from tests.conftest import auth, last_otp, login

API = "/api/v1"


def test_login_requires_otp_then_returns_tokens(client):
    tokens = login(client)
    me = client.get(f"{API}/auth/me", headers=auth(tokens)).json()
    assert me["username"] == "owner"
    assert "owner" in me["roles"]
    assert "users.manage" in me["permissions"]


def test_wrong_password_is_rejected_without_otp(client):
    r = client.post(f"{API}/auth/login", json={"login": "owner", "password": "nope"})
    assert r.status_code == 401


def test_login_by_phone(client):
    r = client.post(f"{API}/auth/login", json={"login": "9000000000", "password": "Owner@12345"})
    assert r.status_code == 200
    assert r.json()["channel"] == "console"


def test_otp_three_attempts_then_locked(client):
    cid = client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"}).json()["challenge_id"]
    code = last_otp()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(3):
        r = client.post(f"{API}/auth/verify-otp", json={"challenge_id": cid, "code": wrong})
        assert r.status_code == 400
    r = client.post(f"{API}/auth/verify-otp", json={"challenge_id": cid, "code": code})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] in {"otp_used", "otp_locked"}


def test_otp_is_single_use(client):
    cid = client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"}).json()["challenge_id"]
    code = last_otp()
    assert client.post(f"{API}/auth/verify-otp", json={"challenge_id": cid, "code": code}).status_code == 200
    r = client.post(f"{API}/auth/verify-otp", json={"challenge_id": cid, "code": code})
    assert r.json()["detail"]["code"] == "otp_used"


def test_otp_expires(client):
    cid = client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"}).json()["challenge_id"]
    with SessionLocal() as db:
        ch = db.get(OtpChallenge, cid)
        ch.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    r = client.post(f"{API}/auth/verify-otp", json={"challenge_id": cid, "code": last_otp()})
    assert r.json()["detail"]["code"] == "otp_expired"


def test_new_otp_voids_previous(client):
    first = client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"}).json()["challenge_id"]
    first_code = last_otp()
    client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"})
    r = client.post(f"{API}/auth/verify-otp", json={"challenge_id": first, "code": first_code})
    assert r.json()["detail"]["code"] == "otp_used"


def test_otp_rate_limited(client):
    for _ in range(5):
        assert client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"}).status_code == 200
    r = client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"})
    assert r.status_code == 429


def test_otp_code_is_not_stored_in_plain_text(client):
    client.post(f"{API}/auth/login", json={"login": "owner", "password": "Owner@12345"})
    code = last_otp()
    with SessionLocal() as db:
        ch = db.query(OtpChallenge).one()
        assert code not in ch.code_hash


def test_refresh_rotates_and_reuse_revokes_family(client):
    tokens = login(client)
    r1 = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    # Replaying the old token is treated as theft: the whole session family dies.
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh(client):
    tokens = login(client)
    assert client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_me_requires_token(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
