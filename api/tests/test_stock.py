import io

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import text

from app.core.db import SessionLocal
from tests.conftest import auth, login
from tests.helpers import API, login_as, make_branch
from tests.test_items_rates import setup_items


def wh(client, owner, branch_id, code, name="Yard"):
    r = client.post(f"{API}/warehouses", json={"branch_id": branch_id, "code": code, "name": name}, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def world(client):
    owner = login(client)
    std, led = setup_items(client, owner)
    chn = make_branch(client, owner)
    cbe = make_branch(client, owner, "CBE", "Coimbatore")
    return {
        "owner": owner,
        "std": std,
        "led": led,
        "chn": chn,
        "cbe": cbe,
        "w1": wh(client, owner, chn["id"], "CHN-WH1"),
        "w2": wh(client, owner, cbe["id"], "CBE-WH1"),
    }


def xlsx(rows, header=("Warehouse code", "Item code", "Available", "Damaged", "Under repair")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, tokens, content, commit=False):
    return client.post(
        f"{API}/stock/opening/import",
        headers=auth(tokens),
        files={"file": ("open.xlsx", content, "application/octet-stream")},
        data={"commit": str(commit).lower()},
    )


def summary(client, tokens, **params):
    return {r["item_code"]: r for r in client.get(f"{API}/stock/summary", params=params, headers=auth(tokens)).json()}


def opening(client, w, rows):
    r = upload(client, w["owner"], xlsx(rows), commit=True)
    assert r.status_code == 200 and r.json()["committed"], r.text


def test_template_downloads(client, world):
    r = client.get(f"{API}/stock/opening/template", headers=auth(world["owner"]))
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert [c.value for c in wb.active[1]][:5] == [
        "Warehouse code",
        "Item code",
        "Available",
        "Damaged",
        "Under repair",
    ]
    assert "Items" in wb.sheetnames and "Warehouses" in wb.sheetnames


def test_opening_preview_then_commit(client, world):
    content = xlsx([("CHN-WH1", "STD-3.0", 500, 10, 5), ("CHN-WH1", "LED-1.5", 800, 0, 0), ("CBE-WH1", "STD-3.0", 200)])
    prev = upload(client, world["owner"], content).json()
    assert prev["ok"] and not prev["committed"]
    assert summary(client, world["owner"]) == {}  # preview posts nothing
    done = upload(client, world["owner"], content, commit=True).json()
    assert done["committed"] and len(done["movements"]) == 2
    s = summary(client, world["owner"])
    assert s["STD-3.0"]["available"] == 700 and s["STD-3.0"]["damaged"] == 10 and s["STD-3.0"]["maintenance"] == 5
    assert summary(client, world["owner"], warehouse_id=world["w2"]["id"])["STD-3.0"]["total"] == 200


def test_opening_errors_reported_per_row(client, world):
    r = upload(
        client,
        world["owner"],
        xlsx(
            [
                ("NOPE", "STD-3.0", 5),
                ("CHN-WH1", "XX", 5),
                ("CHN-WH1", "STD-3.0", -2),
                ("CHN-WH1", "LED-1.5", 1),
                ("CHN-WH1", "LED-1.5", 2),
            ]
        ),
        commit=True,
    )
    body = r.json()
    assert not body["ok"] and not body["committed"]
    rows = {r["row"] for r in body["rows"] if r["errors"]}
    assert {2, 3, 4, 6} <= rows
    bad_header = upload(client, world["owner"], xlsx([], header=("a", "b"))).json()
    assert not bad_header["ok"]


def test_opening_closed_after_other_movement(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100)])
    client.post(
        f"{API}/stock/status-change",
        headers=auth(world["owner"]),
        json={
            "warehouse_id": world["w1"]["id"],
            "item_id": world["std"]["id"],
            "from_status": "available",
            "to_status": "maintenance",
            "qty": 1,
        },
    )
    body = upload(client, world["owner"], xlsx([("CHN-WH1", "LED-1.5", 5)])).json()
    assert not body["ok"]


def test_status_change_rules(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100)])
    o, w1, std = world["owner"], world["w1"]["id"], world["std"]["id"]

    def chg(f, t, q, tokens=o):
        return client.post(
            f"{API}/stock/status-change",
            headers=auth(tokens),
            json={"warehouse_id": w1, "item_id": std, "from_status": f, "to_status": t, "qty": q},
        )

    assert chg("available", "damaged", 10).status_code == 201
    assert chg("damaged", "maintenance", 4).status_code == 201
    assert chg("maintenance", "available", 4).status_code == 201
    assert chg("available", "at_site", 1).status_code == 422  # only dispatch does that
    short = chg("damaged", "maintenance", 50)
    assert short.status_code == 409 and short.json()["detail"]["shortages"]
    s = summary(client, o)["STD-3.0"]
    assert (s["available"], s["damaged"], s["maintenance"], s["total"]) == (94, 6, 0, 100)


def test_write_off_needs_adjust_and_reduces_total(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100, 8)])
    body = {
        "warehouse_id": world["w1"]["id"],
        "item_id": world["std"]["id"],
        "from_status": "damaged",
        "qty": 3,
        "reason": "Bent beyond repair",
    }
    sk = login_as(
        client, world["owner"], "store1", ["storekeeper"], scopes=[{"type": "branch", "id": world["chn"]["id"]}]
    )
    assert client.post(f"{API}/stock/write-off", json=body, headers=auth(sk)).status_code == 403
    assert client.post(f"{API}/stock/write-off", json=body, headers=auth(world["owner"])).status_code == 201
    bad = {**body, "from_status": "available"}
    assert client.post(f"{API}/stock/write-off", json=bad, headers=auth(world["owner"])).status_code == 422
    assert summary(client, world["owner"])["STD-3.0"]["total"] == 105


def test_transfer_send_and_receive_with_shortfall(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100), ("CHN-WH1", "LED-1.5", 50)])
    o, std, led = world["owner"], world["std"]["id"], world["led"]["id"]
    r = client.post(
        f"{API}/stock/transfers",
        headers=auth(o),
        json={
            "from_warehouse_id": world["w1"]["id"],
            "to_warehouse_id": world["w2"]["id"],
            "vehicle_no": "TN 01 AB 1234",
            "lines": [{"item_id": std, "qty": 40}, {"item_id": led, "qty": 20}],
        },
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "in_transit" and t["ref_no"].startswith("TRF-")
    s = summary(client, o)
    assert s["STD-3.0"]["available"] == 60 and s["STD-3.0"]["in_transit"] == 40 and s["STD-3.0"]["total"] == 100

    rc = client.post(
        f"{API}/stock/transfers/{t['id']}/receive",
        headers=auth(o),
        json={"lines": [{"item_id": std, "received": 37, "damaged": 1}, {"item_id": led, "received": 20}]},
    )
    assert rc.status_code == 200, rc.text
    lines = {ln["item_id"]: ln for ln in rc.json()["lines"]}
    assert lines[std]["qty_missing"] == 2
    w2 = summary(client, o, warehouse_id=world["w2"]["id"])["STD-3.0"]
    assert (w2["available"], w2["damaged"]) == (37, 1)
    w1 = summary(client, o, warehouse_id=world["w1"]["id"])["STD-3.0"]
    assert (w1["available"], w1["missing"]) == (60, 2)
    assert summary(client, o)["STD-3.0"]["in_transit"] == 0
    again = client.post(f"{API}/stock/transfers/{t['id']}/receive", headers=auth(o), json={"lines": []})
    assert again.status_code == 400


def test_transfer_cannot_overdraw(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 10)])
    r = client.post(
        f"{API}/stock/transfers",
        headers=auth(world["owner"]),
        json={
            "from_warehouse_id": world["w1"]["id"],
            "to_warehouse_id": world["w2"]["id"],
            "lines": [{"item_id": world["std"]["id"], "qty": 11}],
        },
    )
    assert r.status_code == 409
    assert client.get(f"{API}/stock/transfers", headers=auth(world["owner"])).json() == []


def test_idempotency_key_prevents_double_post(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 10)])
    body = {
        "warehouse_id": world["w1"]["id"],
        "item_id": world["std"]["id"],
        "from_status": "available",
        "to_status": "damaged",
        "qty": 2,
    }
    h = {**auth(world["owner"]), "Idempotency-Key": "abc-123"}
    a = client.post(f"{API}/stock/status-change", json=body, headers=h)
    b = client.post(f"{API}/stock/status-change", json=body, headers=h)
    assert a.status_code == 201 and b.status_code in (200, 201) and a.json()["ref_no"] == b.json()["ref_no"]
    assert summary(client, world["owner"])["STD-3.0"]["damaged"] == 2


def test_stock_check_variances(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100), ("CHN-WH1", "LED-1.5", 50)])
    o, w1, std, led = world["owner"], world["w1"]["id"], world["std"]["id"], world["led"]["id"]
    r = client.post(
        f"{API}/stock/checks",
        headers=auth(o),
        json={"warehouse_id": w1, "lines": [{"item_id": std, "counted": 95}, {"item_id": led, "counted": 50}]},
    )
    assert r.status_code == 201, r.text
    var = {ln["item_id"]: ln["variance"] for ln in r.json()["lines"]}
    assert var == {std: -5, led: 0}
    s = summary(client, o)["STD-3.0"]
    assert (s["available"], s["missing"]) == (95, 5)
    # recount finds 7 more: 5 come back from missing, 2 are new found stock
    r2 = client.post(
        f"{API}/stock/checks", headers=auth(o), json={"warehouse_id": w1, "lines": [{"item_id": std, "counted": 102}]}
    )
    assert r2.status_code == 201
    s = summary(client, o)["STD-3.0"]
    assert (s["available"], s["missing"], s["total"]) == (102, 0, 102)


def test_scope_hides_other_branch_warehouse(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 100), ("CBE-WH1", "STD-3.0", 30)])
    bm = login_as(
        client, world["owner"], "bm1", ["branch_manager"], scopes=[{"type": "branch", "id": world["chn"]["id"]}]
    )
    assert summary(client, bm)["STD-3.0"]["available"] == 100
    r = client.get(f"{API}/stock/summary", params={"warehouse_id": world["w2"]["id"]}, headers=auth(bm))
    assert r.status_code == 404
    mv = client.get(f"{API}/stock/movements", headers=auth(bm)).json()
    assert all(m["warehouse_id"] == world["w1"]["id"] for m in mv) and mv


def test_ledger_is_append_only(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 10)])
    with SessionLocal() as db, pytest.raises(Exception, match="append-only"):
        db.execute(text("UPDATE stock_ledger SET qty = 999"))
        db.commit()


def test_movements_and_audit(client, world):
    opening(client, world, [("CHN-WH1", "STD-3.0", 10)])
    mv = client.get(f"{API}/stock/movements", headers=auth(world["owner"])).json()
    assert mv[0]["kind"] == "opening" and mv[0]["ref_no"].startswith("OPN-") and mv[0]["entries"][0]["qty"] == 10
    log = client.get(f"{API}/audit", params={"action": "stock.opening_imported"}, headers=auth(world["owner"])).json()
    assert log
