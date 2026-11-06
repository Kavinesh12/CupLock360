from datetime import UTC, datetime, timedelta

from tests.conftest import auth, login
from tests.helpers import API, login_as, make_branch


def new_lead(client, tokens, branch_id, **kw):
    r = client.post(f"{API}/leads", json={"company_name": "Sri Balaji Builders", "contact_name": "Mr Balaji",
                                          "phone": "9876500000", "branch_id": branch_id, "city": "Chennai", **kw},
                    headers=auth(tokens))
    assert r.status_code == 201, r.text
    return r.json()


def test_follow_up_moves_status_and_due_list(client):
    owner = login(client)
    b = make_branch(client, owner)
    sales = login_as(client, owner, "sales1", ["sales"])
    lead = new_lead(client, sales, b["id"])
    assert lead["status"] == "new" and lead["assigned_to"] is not None
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = client.post(f"{API}/leads/{lead['id']}/follow-ups", json={"note": "Called, wants 2,000 standards",
                                                                 "next_follow_up_at": soon}, headers=auth(sales))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "contacted" and len(r.json()["follow_ups"]) == 1
    due = client.get(f"{API}/leads?due=true", headers=auth(sales)).json()
    assert [x["id"] for x in due] == [lead["id"]]
    later = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    client.post(f"{API}/leads/{lead['id']}/follow-ups", json={"note": "Sent quote", "status": "quoted",
                                                             "next_follow_up_at": later}, headers=auth(sales))
    assert client.get(f"{API}/leads?due=true", headers=auth(sales)).json() == []


def test_sales_sees_only_own_leads_manager_sees_all(client):
    owner = login(client)
    b = make_branch(client, owner)
    s1 = login_as(client, owner, "sales1", ["sales"])
    s2 = login_as(client, owner, "sales2", ["sales"])
    lead = new_lead(client, s1, b["id"])
    assert client.get(f"{API}/leads", headers=auth(s2)).json() == []
    assert client.get(f"{API}/leads/{lead['id']}", headers=auth(s2)).status_code == 404
    bm = login_as(client, owner, "bm1", ["branch_manager"])
    assert len(client.get(f"{API}/leads", headers=auth(bm)).json()) == 1


def test_lost_needs_reason(client):
    owner = login(client)
    b = make_branch(client, owner)
    lead = new_lead(client, owner, b["id"])
    assert client.patch(f"{API}/leads/{lead['id']}", json={"status": "lost"}, headers=auth(owner)).status_code == 422
    r = client.patch(f"{API}/leads/{lead['id']}", json={"status": "lost", "lost_reason": "Price"}, headers=auth(owner))
    assert r.json()["status"] == "lost"


def test_convert_lead_creates_client_project_site(client):
    owner = login(client)
    b = make_branch(client, owner)
    sales = login_as(client, owner, "sales1", ["sales"])
    lead = new_lead(client, sales, b["id"])
    r = client.post(f"{API}/leads/{lead['id']}/convert",
                    json={"gstin": "33ABCDE1234F1Z5", "project_name": "OMR Tech Park", "site_name": "Tower A"},
                    headers=auth(sales))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["lead"]["status"] == "won"
    assert out["client"]["name"] == "Sri Balaji Builders" and out["client"]["phone"] == "9876500000"
    assert out["client"]["credit_status"] == "pending"
    assert out["project"]["client_id"] == out["client"]["id"]
    assert out["site"]["project_id"] == out["project"]["id"] and out["site"]["city"] == "Chennai"
    again = client.post(f"{API}/leads/{lead['id']}/convert", json={"project_name": "x", "site_name": "y"},
                        headers=auth(sales))
    assert again.status_code == 400


def test_convert_into_existing_client(client):
    owner = login(client)
    b = make_branch(client, owner)
    c = client.post(f"{API}/clients", json={"name": "Kaveri", "branch_id": b["id"]}, headers=auth(owner)).json()
    lead = new_lead(client, owner, b["id"], company_name="Kaveri (new site)")
    out = client.post(f"{API}/leads/{lead['id']}/convert",
                      json={"existing_client_id": c["id"], "project_name": "Ring Road", "site_name": "Pier 3"},
                      headers=auth(owner)).json()
    assert out["client"]["id"] == c["id"] and out["project"]["code"] == f"P-{c['id']:04d}-01"
