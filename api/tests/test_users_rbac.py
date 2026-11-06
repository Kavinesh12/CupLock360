from tests.conftest import auth, login

API = "/api/v1"


def make_user(client, owner_tokens, username, roles, **extra):
    body = {"username": username, "full_name": username.title(), "password": "Passw0rd!x", "roles": roles, **extra}
    r = client.post(f"{API}/users", json=body, headers=auth(owner_tokens))
    assert r.status_code == 201, r.text
    return r.json()


def test_all_twelve_roles_seeded(client):
    owner = login(client)
    roles = client.get(f"{API}/roles", headers=auth(owner)).json()
    assert len(roles) == 12
    assert {r["code"] for r in roles} >= {"owner", "storekeeper", "auditor", "client_portal", "sysadmin"}


def test_staff_cannot_call_owner_only_api(client):
    owner = login(client)
    make_user(client, owner, "store1", ["storekeeper"])
    store = login(client, "store1", "Passw0rd!x")
    assert client.get(f"{API}/users", headers=auth(store)).status_code == 403
    assert client.post(f"{API}/branches", json={"code": "CHN", "name": "Chennai"},
                       headers=auth(store)).status_code == 403
    assert client.get(f"{API}/branches", headers=auth(store)).status_code == 200


def test_sysadmin_cannot_grant_owner(client):
    owner = login(client)
    make_user(client, owner, "admin1", ["sysadmin"])
    admin = login(client, "admin1", "Passw0rd!x")
    r = client.post(f"{API}/users", json={"username": "xone", "full_name": "X", "password": "Passw0rd!x",
                                          "roles": ["owner"]}, headers=auth(admin))
    assert r.status_code == 403
    r = client.post(f"{API}/users", json={"username": "xtwo", "full_name": "X", "password": "Passw0rd!x",
                                          "roles": ["storekeeper"]}, headers=auth(admin))
    assert r.status_code == 201


def test_deactivating_user_revokes_sessions_instantly(client):
    owner = login(client)
    u = make_user(client, owner, "sales1", ["sales"])
    sales = login(client, "sales1", "Passw0rd!x")
    assert client.get(f"{API}/auth/me", headers=auth(sales)).status_code == 200
    client.patch(f"{API}/users/{u['id']}", json={"is_active": False}, headers=auth(owner))
    assert client.get(f"{API}/auth/me", headers=auth(sales)).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": sales["refresh_token"]}).status_code == 401


def test_owner_cannot_deactivate_self(client):
    owner = login(client)
    me = client.get(f"{API}/auth/me", headers=auth(owner)).json()
    r = client.patch(f"{API}/users/{me['id']}", json={"is_active": False}, headers=auth(owner))
    assert r.status_code == 400


def test_branch_scope_limits_branch_list(client):
    owner = login(client)
    chn = client.post(f"{API}/branches", json={"code": "CHN", "name": "Chennai"}, headers=auth(owner)).json()
    client.post(f"{API}/branches", json={"code": "MDU", "name": "Madurai"}, headers=auth(owner))
    make_user(client, owner, "bm1", ["branch_manager"], scopes=[{"type": "branch", "id": chn["id"]}])
    bm = login(client, "bm1", "Passw0rd!x")
    names = [b["name"] for b in client.get(f"{API}/branches", headers=auth(bm)).json()]
    assert names == ["Chennai"]


def test_duplicate_username_conflict(client):
    owner = login(client)
    make_user(client, owner, "dup", ["sales"])
    r = client.post(f"{API}/users", json={"username": "dup", "full_name": "D", "password": "Passw0rd!x",
                                          "roles": ["sales"]}, headers=auth(owner))
    assert r.status_code == 409


def test_user_lookup_available_to_any_role(client):
    owner = login(client)
    make_user(client, owner, "store1", ["storekeeper"])
    sk = login(client, "store1", "Passw0rd!x")
    rows = client.get(f"{API}/users/lookup", headers=auth(sk)).json()
    assert {"id", "full_name"} == set(rows[0])
    assert len(rows) == 2
