from tests.conftest import auth, login
from tests.helpers import API, login_as, make_branch


def test_client_project_site_hierarchy_and_codes(client):
    owner = login(client)
    chn = make_branch(client, owner)
    c = client.post(f"{API}/clients", json={"name": "Kaveri Infra Builders", "branch_id": chn["id"],
                                            "gstin": "33abcde1234f1z5", "credit_limit": "2500000",
                                            "security_deposit": "300000", "credit_status": "approved"},
                    headers=auth(owner))
    assert c.status_code == 201, c.text
    c = c.json()
    assert c["code"] == f"CL-{c['id']:04d}"
    assert c["gstin"] == "33ABCDE1234F1Z5"
    assert c["state"] == "Tamil Nadu" and c["state_code"] == "33"
    assert c["credit_limit"] == "2500000.00"

    p = client.post(f"{API}/clients/{c['id']}/projects", json={"name": "OMR Tech Park"}, headers=auth(owner)).json()
    assert p["code"] == f"P-{c['id']:04d}-01" and p["branch_id"] == chn["id"]
    s = client.post(f"{API}/projects/{p['id']}/sites", json={"name": "Tower A", "city": "Sholinganallur"},
                    headers=auth(owner)).json()
    assert s["code"].startswith("S-")

    detail = client.get(f"{API}/clients/{c['id']}", headers=auth(owner)).json()
    assert detail["projects"][0]["sites"][0]["name"] == "Tower A"
    sites = client.get(f"{API}/sites?client_id={c['id']}", headers=auth(owner)).json()
    assert sites[0]["client_name"] == "Kaveri Infra Builders"


def test_gstin_from_other_state_sets_igst_state(client):
    owner = login(client)
    b = make_branch(client, owner)
    c = client.post(f"{API}/clients", json={"name": "Bangalore Build", "branch_id": b["id"],
                                            "gstin": "29ABCDE1234F1Z5"}, headers=auth(owner)).json()
    assert c["state_code"] == "29" and c["state"] == "Karnataka"


def test_invalid_gstin_rejected_and_duplicate_conflicts(client):
    owner = login(client)
    b = make_branch(client, owner)
    r = client.post(f"{API}/clients", json={"name": "Bad", "branch_id": b["id"], "gstin": "123"}, headers=auth(owner))
    assert r.status_code == 422
    body = {"name": "One", "branch_id": b["id"], "gstin": "33ABCDE1234F1Z5"}
    assert client.post(f"{API}/clients", json=body, headers=auth(owner)).status_code == 201
    assert client.post(f"{API}/clients", json={**body, "name": "Two"}, headers=auth(owner)).status_code == 409


def test_sales_cannot_set_credit_terms(client):
    owner = login(client)
    b = make_branch(client, owner)
    sales = login_as(client, owner, "sales1", ["sales"])
    c = client.post(f"{API}/clients", json={"name": "Sri Balaji", "branch_id": b["id"], "credit_limit": "9999999",
                                            "credit_status": "approved"}, headers=auth(sales)).json()
    assert c["credit_limit"] == "0.00" and c["credit_status"] == "pending"
    r = client.patch(f"{API}/clients/{c['id']}", json={"credit_limit": "100"}, headers=auth(sales))
    assert r.status_code == 403
    r = client.patch(f"{API}/clients/{c['id']}", json={"contact_name": "Mr Balaji"}, headers=auth(sales))
    assert r.status_code == 200
    acc = login_as(client, owner, "acc1", ["accounts_manager"])
    r = client.patch(f"{API}/clients/{c['id']}", json={"credit_limit": "500000", "credit_status": "approved"},
                     headers=auth(acc))
    assert r.status_code == 403  # accounts manager can set credit but has no clients.manage
    r = client.patch(f"{API}/clients/{c['id']}", json={"credit_limit": "500000", "credit_status": "approved"},
                     headers=auth(owner))
    assert r.json()["credit_status"] == "approved"


def test_branch_scope_hides_other_branch_clients(client):
    owner = login(client)
    chn = make_branch(client, owner, "CHN", "Chennai")
    mdu = make_branch(client, owner, "MDU", "Madurai")
    client.post(f"{API}/clients", json={"name": "Chennai Co", "branch_id": chn["id"]}, headers=auth(owner))
    other = client.post(f"{API}/clients", json={"name": "Madurai Co", "branch_id": mdu["id"]},
                        headers=auth(owner)).json()
    bm = login_as(client, owner, "bm1", ["branch_manager"], scopes=[{"type": "branch", "id": chn["id"]}])
    names = [c["name"] for c in client.get(f"{API}/clients", headers=auth(bm)).json()]
    assert names == ["Chennai Co"]
    assert client.get(f"{API}/clients/{other['id']}", headers=auth(bm)).status_code == 404
    r = client.post(f"{API}/clients", json={"name": "Sneaky", "branch_id": mdu["id"]}, headers=auth(bm))
    assert r.status_code == 403


def test_storekeeper_cannot_create_clients(client):
    owner = login(client)
    b = make_branch(client, owner)
    sk = login_as(client, owner, "store1", ["storekeeper"])
    assert client.post(f"{API}/clients", json={"name": "X Co", "branch_id": b["id"]},
                       headers=auth(sk)).status_code == 403
