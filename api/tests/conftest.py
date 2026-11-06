import os

os.environ["CUPLOCK_ENV"] = "test"
os.environ.setdefault("CUPLOCK_DATABASE_URL", "postgresql+psycopg://cuplock:cuplock@localhost:5432/cuplock_test")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services.notify import DEV_OUTBOX  # noqa: E402

HERE = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(autouse=True)
def fresh_db():
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "alembic"))
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed(db)
    DEV_OUTBOX.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def last_otp() -> str:
    return DEV_OUTBOX[-1]["code"]


def login(client, username="owner", password="Owner@12345") -> dict:
    r = client.post("/api/v1/auth/login", json={"login": username, "password": password})
    assert r.status_code == 200, r.text
    r2 = client.post("/api/v1/auth/verify-otp", json={"challenge_id": r.json()["challenge_id"], "code": last_otp()})
    assert r2.status_code == 200, r2.text
    return r2.json()


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
