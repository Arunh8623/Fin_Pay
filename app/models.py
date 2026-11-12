import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _now():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    user = "user"
    merchant = "merchant"
    admin = "admin"


class Account(Base):
    """A FinPay account (user, merchant or admin). Every account has a wallet.
    Money is stored as integer minor units (paise) to avoid float errors."""

    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("balance_minor >= 0", name="ck_balance_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    business_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.user.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Users/admin are authorized on sign-up; merchants need admin approval (FR4)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Transaction(Base):
    """Created only for successful payments. Also acts as the 'already processed' marker."""

    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("payer_id", "payment_request_id", name="uq_payer_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_request_id: Mapped[str] = mapped_column(String(64))
    payer_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    payee_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
