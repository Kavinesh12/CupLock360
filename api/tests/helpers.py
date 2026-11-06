from tests.conftest import auth, login

API = "/api/v1"


def make_user(client, owner_tokens, username, roles, **extra):
    body = {"username": username, "full_name": username.title(), "password": "Passw0rd!x", "roles": roles, **extra}
    r = client.post(f"{API}/users", json=body, headers=auth(owner_tokens))
    assert r.status_code == 201, r.text
    return r.json()


def login_as(client, owner_tokens, username, roles, **extra):
    make_user(client, owner_tokens, username, roles, **extra)
    return login(client, username, "Passw0rd!x")


def make_branch(client, owner_tokens, code="CHN", name="Chennai"):
    r = client.post(f"{API}/branches", json={"code": code, "name": name}, headers=auth(owner_tokens))
    assert r.status_code == 201, r.text
    return r.json()
