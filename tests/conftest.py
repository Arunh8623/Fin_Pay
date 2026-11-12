import os
import tempfile

# must be set before the app is imported
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


_counter = iter(range(1, 10_000))


def make_account(client, role="user", authorize=False, balance=None):
    n = next(_counter)
    email = f"{role}{n}@example.com"
    body = {"email": email, "password": "Password123", "full_name": f"{role} {n}", "role": role}
    if role == "merchant":
        body["business_name"] = f"Shop {n}"
    acc = client.post("/auth/register", json=body).json()
    if authorize:
        admin = login(client, "admin@finpay.com", "Admin@12345")
        client.post(f"/admin/merchants/{acc['id']}/authorize", headers=admin)
    headers = login(client, email, "Password123")
    if balance:
        client.post("/wallet/topup", json={"amount": balance}, headers=headers)
    return acc, headers


def login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
