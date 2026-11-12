from sqlalchemy import select

from app.database import SessionLocal
from app.models import Account, Transaction
from app.services.payment import process_payment
from tests.conftest import login, make_account


def pay(client, headers, payee_id, amount, rid="r-1", **extra):
    return client.post(
        "/payments",
        json={"payment_request_id": rid, "payee_id": payee_id, "amount": amount, **extra},
        headers=headers,
    )


def balance(client, headers):
    return client.get("/wallet/balance", headers=headers).json()["balance"]


# ---------- FR1 / FR4 / NFR5 authentication & authorization ----------
def test_requires_authentication(client):
    assert client.get("/wallet/balance").status_code == 401
    assert client.get("/wallet/balance", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_wrong_password(client):
    acc, _ = make_account(client)
    r = client.post("/auth/login", data={"username": acc["email"], "password": "wrong-pass"})
    assert r.status_code == 401


def test_unauthorized_merchant_blocked_until_approved(client):
    merchant, h = make_account(client, "merchant")
    assert merchant["is_authorized"] is False
    assert client.get("/merchant/transactions", headers=h).status_code == 403
    assert client.get("/wallet/balance", headers=h).status_code == 403
    admin = login(client, "admin@finpay.com", "Admin@12345")
    assert client.post(f"/admin/merchants/{merchant['id']}/authorize", headers=admin).status_code == 200
    assert client.get("/merchant/transactions", headers=h).status_code == 200


def test_admin_endpoints_forbidden_for_users(client):
    _, h = make_account(client)
    assert client.get("/admin/merchants", headers=h).status_code == 403


# ---------- FR3 balance ----------
def test_balance_and_topup(client):
    _, h = make_account(client, balance="250.50")
    assert balance(client, h) == "250.50"


# ---------- FR2 payments ----------
def test_successful_payment(client):
    _, uh = make_account(client, balance="100")
    m, mh = make_account(client, "merchant", authorize=True)
    r = pay(client, uh, m["id"], "40.25")
    assert r.status_code == 201 and r.json()["success"] is True
    assert balance(client, uh) == "59.75"
    assert balance(client, mh) == "40.25"
    assert len(client.get("/merchant/transactions", headers=mh).json()) == 1
    assert len(client.get("/payments", headers=uh).json()) == 1


def test_user_to_user_payment(client):
    _, a = make_account(client, balance="50")
    b, bh = make_account(client)
    assert pay(client, a, b["id"], "10").status_code == 201
    assert balance(client, bh) == "10.00"


def test_zero_and_negative_rejected(client):
    _, uh = make_account(client, balance="100")
    m, _ = make_account(client, "merchant", authorize=True)
    assert pay(client, uh, m["id"], "0", rid="z").status_code == 422
    r = pay(client, uh, m["id"], "-5", rid="n")
    assert r.status_code == 422 and "greater than 0" in r.json()["reason"]
    assert balance(client, uh) == "100.00"


def test_missing_amount_and_bad_precision_and_limits(client):
    _, uh = make_account(client, balance="100")
    m, _ = make_account(client, "merchant", authorize=True)
    assert pay(client, uh, m["id"], None, rid="a").status_code == 422
    assert pay(client, uh, m["id"], "1.234", rid="b").status_code == 422
    assert pay(client, uh, m["id"], "999999", rid="c").status_code == 422


def test_insufficient_balance_creates_no_record(client):
    _, uh = make_account(client, balance="10")
    m, mh = make_account(client, "merchant", authorize=True)
    r = pay(client, uh, m["id"], "50")
    assert r.status_code == 402 and r.json()["success"] is False
    assert balance(client, uh) == "10.00" and balance(client, mh) == "0.00"
    assert client.get("/payments", headers=uh).json() == []


def test_duplicate_request_rejected_and_not_charged_twice(client):
    _, uh = make_account(client, balance="100")
    m, _ = make_account(client, "merchant", authorize=True)
    assert pay(client, uh, m["id"], "30", rid="dup").status_code == 201
    r = pay(client, uh, m["id"], "30", rid="dup")
    assert r.status_code == 409 and "already processed" in r.json()["reason"]
    assert balance(client, uh) == "70.00"


def test_payee_rules(client):
    _, uh = make_account(client, balance="100")
    pending, _ = make_account(client, "merchant")  # not authorized
    assert pay(client, uh, pending["id"], "5", rid="p1").status_code == 403
    assert pay(client, uh, 999999, "5", rid="p2").status_code == 422  # missing payee
    me = client.get("/users/me", headers=uh).json()
    assert pay(client, uh, me["id"], "5", rid="p3").status_code == 422  # self payment


def test_merchant_cannot_make_payments(client):
    _, mh = make_account(client, "merchant", authorize=True)
    other, _ = make_account(client)
    assert pay(client, mh, other["id"], "1").status_code == 403


# ---------- atomic rollback (Part B4 / D) ----------
def test_rollback_when_transaction_record_fails(client, monkeypatch):
    _, uh = make_account(client, balance="100")
    m, mh = make_account(client, "merchant", authorize=True)
    with SessionLocal() as db:
        payer = db.scalar(select(Account).where(Account.email == client.get("/users/me", headers=uh).json()["email"]))
        payee = db.get(Account, m["id"])

        class Req:
            payment_request_id = "boom"
            amount = "20"
            currency = None
            description = None

        # make the transaction insert blow up after debit & credit were executed
        original_add = db.add
        monkeypatch.setattr(db, "add", lambda *_: (_ for _ in ()).throw(RuntimeError("db down")))
        result = process_payment(db, payer, payee, Req())
        monkeypatch.setattr(db, "add", original_add)
    assert result.success is False and "rolled back" in result.reason
    assert balance(client, uh) == "100.00" and balance(client, mh) == "0.00"
    with SessionLocal() as db:
        assert db.scalar(select(Transaction).where(Transaction.payment_request_id == "boom")) is None


def test_process_payment_never_raises_on_none(client):
    with SessionLocal() as db:
        res = process_payment(db, None, None, None)
    assert res.success is False


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
