import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import select, text

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Account, Role
from .routers import admin, auth, merchant, payments, wallet
from .security import hash_password

log = logging.getLogger("finpay")


def seed_admin():
    with SessionLocal() as db:
        if not db.scalar(select(Account.id).where(Account.email == settings.admin_email.lower())):
            db.add(
                Account(
                    email=settings.admin_email.lower(),
                    full_name="FinPay Admin",
                    password_hash=hash_password(settings.admin_password),
                    role=Role.admin.value,
                    is_authorized=True,
                    currency=settings.currency,
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_admin()
    yield


app = FastAPI(
    title="FinPay API",
    version="1.0.0",
    description="Wallet payments between users and merchants (FR1-FR4, NFR1-NFR5).",
    lifespan=lifespan,
)


@app.middleware("http")
async def timing(request: Request, call_next):
    """NFR1/NFR2: expose request time and log requests that exceed the targets."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.3f}"
    limit = {"/auth/login": settings.auth_time_limit, "/payments": settings.payment_time_limit}.get(request.url.path)
    if limit and elapsed > limit:
        log.warning("%s took %.2fs (limit %.1fs)", request.url.path, elapsed, limit)
    return response


@app.get("/health", tags=["System"])  # NFR4: use for uptime monitoring / load balancer checks
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


for r in (auth.router, wallet.router, payments.router, merchant.router, admin.router):
    app.include_router(r)
