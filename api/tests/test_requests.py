from decimal import Decimal

import pytest

from tests.conftest import auth, last_otp, login
from tests.helpers import API, login_as, make_branch
from tests.test_items_rates import setup_items
from tests.test_stock import opening, summary, wh


@pytest.fixture
def ops(client):
    owner = login(client)
    std, led = setup_items(client, owner)
    chn = make_branch(client, owner)
    w1 = wh(client, owner, chn["id"], "CHN-WH1")
    w2 = wh(client, owner, chn["id"], "CHN-WH2")
    c = client.post(f"{API}/clients", json={"name": "Kaveri Infra", "branch_id": chn["id"]}, headers=auth(owner)).json()
    p = client.post(f"{API}/clients/{c['id']}/projects", json={"name": "Tower A"}, headers=auth(owner)).json()
    s = client.post(f"{API}/projects/{p['id']}/sites", json={"name": "Sholinganallur"}, headers=auth(owner)).json()
    s_ka = client.post(
        f"{API}/projects/{p['id']}/sites", json={"name": "Hosur", "state_code": "29"}, headers=auth(owner)
    ).json()
    r = client.post(
        f"{API}/rate-cards",
        headers=auth(owner),
        json={
            "name": "Std",
            "valid_from": "2026-01-01",
            "min_days": 30,
            "lines": [{"item_id": std["id"], "rate_per_day": "4.50"}, {"item_id": led["id"], "rate_per_day": "2"}],
        },
    )
    assert r.status_code == 201, r.text
    w = {"owner": owner}
    opening(client, w, [("CHN-WH1", "STD-3.0", 1000), ("CHN-WH1", "LED-1.5", 500), ("CHN-WH2", "STD-3.0", 300)])
    return {
        "owner": owner,
        "std": std,
        "led": led,
        "chn": chn,
        "w1": w1,
        "w2": w2,
        "client": c,
        "site": s,
        "site_ka": s_ka,
    }


def new_request(client, o, tokens=None, **kw):
    body = {
        "site_id": o["site"]["id"],
        "warehouse_id": o["w1"]["id"],
        "required_on": "2026-11-10",
        "duration_days": 45,
        "transport_charge": "5000",
        "lines": [{"item_id": o["std"]["id"], "qty": 400}, {"item_id": o["led"]["id"], "qty": 200}],
        **kw,
    }
    r = client.post(f"{API}/requests", json=body, headers=auth(tokens or o["owner"]))
    assert r.status_code == 201, r.text
    return r.json()


def approve(client, tokens, req, qtys):
    lines = [{"item_id": k, "qty": v} for k, v in qtys.items()]
    r = client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": lines}, headers=auth(tokens))
    assert r.status_code == 200, r.text
    return client.post(
        f"{API}/requests/{req['id']}/approve",
        headers=auth(tokens),
        json={"challenge_id": r.json()["challenge_id"], "code": last_otp(), "lines": lines},
    )


def test_estimate_and_gst(client, ops):
    req = new_request(client, ops)
    # 400 x 4.50 x 45 + 200 x 2 x 45 = 81000 + 18000; + 5000 transport; 18% GST intra-state
    assert Decimal(req["est_rent"]) == Decimal("99000.00")
    assert Decimal(req["est_taxable"]) == Decimal("104000.00")
    assert Decimal(req["est_gst"]) == Decimal("18720.00")
    assert Decimal(req["est_total"]) == Decimal("122720.00")
    # minimum period applies and inter-state uses IGST
    r = client.post(
        f"{API}/requests/estimate",
        headers=auth(ops["owner"]),
        json={
            "site_id": ops["site_ka"]["id"],
            "duration_days": 10,
            "warehouse_id": ops["w1"]["id"],
            "lines": [{"item_id": ops["std"]["id"], "qty": 1200}],
        },
    ).json()
    assert r["lines"][0]["days"] == 30 and Decimal(r["igst"]) > 0 and Decimal(r["cgst"]) == 0
    av = r["availability"][0]
    assert av["available"] == 1000 and av["short"] == 200 and av["elsewhere"][0]["available"] == 300


def test_full_flow_request_approve_dispatch_receive(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    sales = login_as(client, o, "sales1", ["sales"])
    req = new_request(client, ops, tokens=sales)
    assert req["status"] == "submitted" and req["ref_no"] == "REQ-000001"

    # partial approval: 350 of 400 standards
    r = approve(client, o, req, {std: 350, led: 200})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    s = summary(client, o, warehouse_id=ops["w1"]["id"])
    assert (s["STD-3.0"]["available"], s["STD-3.0"]["reserved"]) == (650, 350)

    st = login_as(client, o, "store1", ["dispatch"])
    d = client.post(
        f"{API}/requests/{req['id']}/dispatches",
        headers=auth(st),
        json={"vehicle_no": "TN09AB1234", "lines": [{"item_id": std, "qty": 300}, {"item_id": led, "qty": 200}]},
    )
    assert d.status_code == 201, d.text
    d = d.json()
    assert d["challan_no"].startswith("DC/CHN/2026-27/0000")
    got = client.get(f"{API}/requests/{req['id']}", headers=auth(o)).json()
    assert got["status"] == "part_dispatched"
    assert summary(client, o)["STD-3.0"]["in_transit"] == 300

    pdf = client.get(f"{API}/dispatches/{d['id']}/challan.pdf", headers=auth(st))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    rc = client.post(
        f"{API}/dispatches/{d['id']}/receive",
        headers=auth(sales),
        json={
            "receiver_name": "Murugan",
            "lines": [{"item_id": std, "received": 298}, {"item_id": led, "received": 200}],
        },
    )
    assert rc.status_code == 200, rc.text
    s = summary(client, o)["STD-3.0"]
    assert (s["at_site"], s["missing"], s["reserved"], s["in_transit"]) == (298, 2, 50, 0)

    # close the rest: 50 reserved go back to available
    cl = client.post(f"{API}/requests/{req['id']}/close", json={"reason": "Site has enough"}, headers=auth(st))
    assert cl.status_code == 200 and cl.json()["status"] == "closed"
    s = summary(client, o)["STD-3.0"]
    assert s["reserved"] == 0 and s["total"] == 1300


def test_otp_is_bound_to_quantities_and_version(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    req = new_request(client, ops)
    lines = [{"item_id": std, "qty": 400}, {"item_id": led, "qty": 200}]
    ch = client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": lines}, headers=auth(o)).json()
    code = last_otp()
    # different quantities with the same OTP -> rejected
    other = [{"item_id": std, "qty": 300}, {"item_id": led, "qty": 200}]
    r = client.post(
        f"{API}/requests/{req['id']}/approve",
        headers=auth(o),
        json={"challenge_id": ch["challenge_id"], "code": code, "lines": other},
    )
    assert r.status_code == 400 and r.json()["detail"]["code"] == "otp_wrong_transaction"
    # amendment bumps the version, so the old OTP no longer fits
    body = {
        "site_id": ops["site"]["id"],
        "warehouse_id": ops["w1"]["id"],
        "required_on": "2026-11-10",
        "duration_days": 45,
        "lines": lines,
    }
    am = client.put(f"{API}/requests/{req['id']}", json=body, headers=auth(o))
    assert am.json()["version"] == 2
    r = client.post(
        f"{API}/requests/{req['id']}/approve",
        headers=auth(o),
        json={"challenge_id": ch["challenge_id"], "code": code, "lines": lines},
    )
    assert r.status_code == 400
    # wrong code is rejected
    ch = client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": lines}, headers=auth(o)).json()
    r = client.post(
        f"{API}/requests/{req['id']}/approve",
        headers=auth(o),
        json={
            "challenge_id": ch["challenge_id"],
            "code": "000000" if last_otp() != "000000" else "111111",
            "lines": lines,
        },
    )
    assert r.status_code == 400


def test_amend_after_approval_releases_reservation(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    req = new_request(client, ops)
    assert approve(client, o, req, {std: 400, led: 200}).status_code == 200
    assert summary(client, o)["STD-3.0"]["reserved"] == 400
    body = {
        "site_id": ops["site"]["id"],
        "warehouse_id": ops["w1"]["id"],
        "required_on": "2026-11-12",
        "duration_days": 60,
        "lines": [{"item_id": std, "qty": 500}],
    }
    r = client.put(f"{API}/requests/{req['id']}", json=body, headers=auth(o)).json()
    assert r["status"] == "submitted" and r["approved_by"] is None
    assert summary(client, o)["STD-3.0"]["reserved"] == 0


def test_approval_limit_self_approval_and_credit_hold(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    bm = login_as(client, o, "bm1", ["branch_manager"], approval_limit="50000")
    req = new_request(client, ops)  # ~1.2 lakh
    lines = [{"item_id": std, "qty": 400}, {"item_id": led, "qty": 200}]
    r = client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": lines}, headers=auth(bm))
    assert r.status_code == 403 and "limit" in r.json()["detail"]
    # a smaller approval is within the limit
    small = [{"item_id": std, "qty": 100}, {"item_id": led, "qty": 0}]
    assert (
        client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": small}, headers=auth(bm)).status_code
        == 200
    )
    # own request
    mine = new_request(client, ops, tokens=bm)
    r = client.post(f"{API}/requests/{mine['id']}/approval-otp", json={"lines": lines}, headers=auth(bm))
    assert r.status_code == 403
    # credit hold blocks approval
    client.patch(f"{API}/clients/{ops['client']['id']}", json={"credit_status": "hold"}, headers=auth(o))
    r = client.post(f"{API}/requests/{req['id']}/approval-otp", json={"lines": lines}, headers=auth(o))
    assert r.status_code == 409 and "hold" in r.json()["detail"]


def test_cannot_approve_more_than_available(client, ops):
    req = new_request(client, ops, lines=[{"item_id": ops["std"]["id"], "qty": 1200}])
    r = client.post(
        f"{API}/requests/{req['id']}/approval-otp",
        headers=auth(ops["owner"]),
        json={"lines": [{"item_id": ops["std"]["id"], "qty": 1200}]},
    )
    assert r.status_code == 409 and r.json()["detail"]["shortages"][0]["available"] == 1000


def test_reject_and_cancel(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    a = new_request(client, ops)
    assert (
        client.post(f"{API}/requests/{a['id']}/reject", json={"reason": "Duplicate"}, headers=auth(o)).json()["status"]
        == "rejected"
    )
    b = new_request(client, ops)
    approve(client, o, b, {std: 400, led: 200})
    c = client.post(f"{API}/requests/{b['id']}/cancel", json={"reason": "Project on hold"}, headers=auth(o)).json()
    assert c["status"] == "cancelled" and summary(client, o)["STD-3.0"]["reserved"] == 0


def test_dispatch_rules(client, ops):
    o, std, led = ops["owner"], ops["std"]["id"], ops["led"]["id"]
    req = new_request(client, ops)
    d = {"lines": [{"item_id": std, "qty": 10}]}
    assert client.post(f"{API}/requests/{req['id']}/dispatches", json=d, headers=auth(o)).status_code == 400
    approve(client, o, req, {std: 100, led: 0})
    too_many = {"lines": [{"item_id": std, "qty": 101}]}
    assert client.post(f"{API}/requests/{req['id']}/dispatches", json=too_many, headers=auth(o)).status_code == 422
    sales = login_as(client, o, "sales2", ["sales"])
    assert client.post(f"{API}/requests/{req['id']}/dispatches", json=d, headers=auth(sales)).status_code == 403
    ok = client.post(
        f"{API}/requests/{req['id']}/dispatches", json={"lines": [{"item_id": std, "qty": 100}]}, headers=auth(o)
    )
    assert ok.status_code == 201
    assert client.get(f"{API}/requests/{req['id']}", headers=auth(o)).json()["status"] == "dispatched"


def test_site_scope_sees_only_own_site(client, ops):
    o = ops["owner"]
    new_request(client, ops)
    new_request(client, ops, site_id=ops["site_ka"]["id"])
    sm = login_as(client, o, "sm1", ["site_manager"], scopes=[{"type": "site", "id": ops["site"]["id"]}])
    rows = client.get(f"{API}/requests", headers=auth(sm)).json()
    assert len(rows) == 1 and rows[0]["site_id"] == ops["site"]["id"]
