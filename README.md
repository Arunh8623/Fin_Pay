# FinPay API (FastAPI)

Wallet payment service built from the FinPay FR/NFR document.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env  (then edit SECRET_KEY)
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs (Swagger UI). Click **Authorize** and log in with email + password.

Default admin (created on first start, change it in `.env`): `admin@finpay.com` / `Admin@12345`

## Run tests
```bash
python -m pytest -q
```

## Run with Docker
```bash
docker build -t finpay .
docker run -p 8000:8000 -e SECRET_KEY=change-me finpay
```

## Quick demo flow
1. `POST /auth/register` - create a user (`role: user`) and a merchant (`role: merchant`, with `business_name`).
2. `POST /auth/login` as admin, then `POST /admin/merchants/{id}/authorize` to approve the merchant.
3. Log in as the user, `POST /wallet/topup` (demo only), then `POST /payments`:
```json
{"payment_request_id": "order-1001", "payee_id": 2, "amount": "250.00", "description": "Order 1001"}
```
4. `GET /wallet/balance`, `GET /payments` (history), `GET /merchant/transactions` (merchant view).

## Requirement mapping
| Requirement | Implementation |
|---|---|
| FR1 / NFR5 authenticate + authorize users | JWT login, role checks in `app/deps.py` |
| FR2 payments to users or merchants | `POST /payments` -> `process_payment()` (`app/services/payment.py`); both payer and payee must be active; merchants must be authorized |
| FR3 check own balance | `GET /wallet/balance` |
| FR4 authenticate + authorize merchants | merchants register as *unauthorized*; an admin approves them; unauthorized merchants get 403 on all payment operations |
| FR5 cashback | **Not implemented** - marked *Reject* in the document (eligibility, expiry and reconciliation rules undefined) |
| NFR1 / NFR2 (3 s auth, 4 s payment) | Fast PBKDF2 hashing + single-transaction payment; `X-Process-Time` header and slow-request warnings |
| NFR3 10,000 concurrent requests | Stateless async app; scale with `--workers`, multiple containers and PostgreSQL (see below) |
| NFR4 24/7 availability | `GET /health` for load balancer / uptime checks |

## Decisions for the gaps listed in Part B / D
| Gap | Decision (configurable in `.env`) |
|---|---|
| Amount limits and precision | Min 0.01, max 100000.00, max 2 decimals, stored as integer paise |
| Missing/null wallet, merchant, payment_request | Rejected with reason (HTTP 422), never an exception |
| Duplicate detection | Same `payment_request_id` from the same payer; rejected (HTTP 409). Checked before the balance check so retries get a stable answer |
| Zero/negative amount | Rejected, reason "Payment amount must be greater than 0." |
| Insufficient balance | Rejected (HTTP 402), no balances change, no transaction record |
| Partial failure (debit/credit/record) | Single DB transaction; everything is rolled back |
| Merchant authorization | Must be admin-approved before receiving/handling payments |
| Currency | INR only (`CURRENCY`) |
| Transaction record | id, payment_request_id, payer_id, payee_id, amount, currency, status, description, created_at |

## Production notes
- SQLite is the default for easy setup. For high concurrency use PostgreSQL:
  `DATABASE_URL=postgresql+psycopg2://user:pass@host/finpay` and `pip install psycopg2-binary`.
- Set a strong `SECRET_KEY` and change the admin password.
- `POST /wallet/topup` is a demo helper; replace with a real payment gateway.
- Use Alembic migrations instead of `create_all` for schema changes.
