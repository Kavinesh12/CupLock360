from tests.conftest import auth, login
from tests.helpers import API, make_branch


def setup_items(client, owner):
    std = client.post(f"{API}/items", json={"code": "STD-3.0", "name": "Cuplock standard 3.0 m", "category": "standard",
                                            "size_m": "3.0", "replacement_cost": "2850", "hsn_sac": "997319"},
                      headers=auth(owner))
    assert std.status_code == 201, std.text
    led = client.post(f"{API}/items", json={"code": "LED-1.5", "name": "Ledger 1.5 m", "category": "ledger",
                                            "size_m": "1.5"}, headers=auth(owner)).json()
    return std.json(), led


def test_item_code_unique(client):
    owner = login(client)
    setup_items(client, owner)
    body = {"code": "STD-3.0", "name": "dup", "category": "standard"}
    r = client.post(f"{API}/items", json=body, headers=auth(owner))
    assert r.status_code == 409


def test_most_specific_rate_card_wins(client):
    owner = login(client)
    std, led = setup_items(client, owner)
    b = make_branch(client, owner)
    c = client.post(f"{API}/clients", json={"name": "Kaveri", "branch_id": b["id"]}, headers=auth(owner)).json()
    p = client.post(f"{API}/clients/{c['id']}/projects", json={"name": "Flyover"}, headers=auth(owner)).json()

    def card(name, lines, **kw):
        r = client.post(f"{API}/rate-cards", json={"name": name, "valid_from": "2026-01-01", "lines": lines, **kw},
                        headers=auth(owner))
        assert r.status_code == 201, r.text
        return r.json()

    card("Standard 2026", [{"item_id": std["id"], "rate_per_day": "5.00"}, {"item_id": led["id"], "rate_per_day": "3"}])
    card("Kaveri agreed", [{"item_id": std["id"], "rate_per_day": "4.50"}], client_id=c["id"])
    card("Flyover special", [{"item_id": std["id"], "rate_per_day": "4.25"}], project_id=p["id"], min_days=45)

    def rates(**params):
        q = "&".join([f"item_ids={std['id']}", f"item_ids={led['id']}", "on=2026-11-06"]
                     + [f"{k}={v}" for k, v in params.items()])
        return {r["item_id"]: r for r in client.get(f"{API}/rates/effective?{q}", headers=auth(owner)).json()}

    r = rates()
    assert r[std["id"]]["rate_per_day"] == "5.00" and r[std["id"]]["level"] == "standard"
    r = rates(client_id=c["id"])
    assert r[std["id"]]["rate_per_day"] == "4.50" and r[led["id"]]["rate_per_day"] == "3.00"
    r = rates(project_id=p["id"])
    assert r[std["id"]]["rate_per_day"] == "4.25" and r[std["id"]]["min_days"] == 45
    assert r[led["id"]]["level"] == "standard"


def test_expired_card_is_ignored(client):
    owner = login(client)
    std, _ = setup_items(client, owner)
    client.post(f"{API}/rate-cards", json={"name": "Old", "valid_from": "2025-01-01", "valid_to": "2025-12-31",
                                           "lines": [{"item_id": std["id"], "rate_per_day": "9"}]}, headers=auth(owner))
    r = client.get(f"{API}/rates/effective?item_ids={std['id']}&on=2026-11-06", headers=auth(owner)).json()
    assert r == []


def test_rate_card_validation(client):
    owner = login(client)
    std, _ = setup_items(client, owner)
    dup = [{"item_id": std["id"], "rate_per_day": "1"}, {"item_id": std["id"], "rate_per_day": "2"}]
    assert client.post(f"{API}/rate-cards", json={"name": "Dup", "valid_from": "2026-01-01", "lines": dup},
                       headers=auth(owner)).status_code == 422
    assert client.post(f"{API}/rate-cards", json={"name": "Bad", "valid_from": "2026-01-01",
                                                  "lines": [{"item_id": 9999, "rate_per_day": "1"}]},
                       headers=auth(owner)).status_code == 422


def test_update_rate_card_replaces_lines(client):
    owner = login(client)
    std, led = setup_items(client, owner)
    cid = client.post(f"{API}/rate-cards", json={"name": "Std", "valid_from": "2026-01-01",
                                                 "lines": [{"item_id": std["id"], "rate_per_day": "5"}]},
                      headers=auth(owner)).json()["id"]
    r = client.put(f"{API}/rate-cards/{cid}", json={"name": "S2", "valid_from": "2026-01-01",
                                                    "lines": [{"item_id": led["id"], "rate_per_day": "2"}]},
                   headers=auth(owner))
    assert r.status_code == 200, r.text
    assert [ln["item_id"] for ln in r.json()["lines"]] == [led["id"]]
