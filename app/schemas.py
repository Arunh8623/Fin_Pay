from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["user", "merchant"] = "user"
    business_name: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def merchant_needs_business_name(self):
        if self.role == "merchant" and not self.business_name:
            raise ValueError("business_name is required for merchants")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AccountOut(BaseModel):
    id: int
    email: str
    full_name: str
    business_name: str | None
    role: str
    is_active: bool
    is_authorized: bool
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    balance: Decimal
    currency: str


class TopUpRequest(BaseModel):
    amount: Decimal


class PaymentRequestIn(BaseModel):
    """payment_request: `payment_request_id` is the idempotency key (Part B duplicate rule)."""

    payment_request_id: str = Field(min_length=1, max_length=64)
    payee_id: int
    amount: Decimal | None = None  # validated in the service so rejections carry a reason
    currency: str | None = None
    description: str | None = Field(default=None, max_length=255)


class PaymentOut(BaseModel):
    success: bool
    reason: str
    transaction: "TransactionOut | None" = None


class TransactionOut(BaseModel):
    id: str
    payment_request_id: str
    payer_id: int
    payee_id: int
    amount: Decimal
    currency: str
    status: str
    description: str | None
    created_at: datetime


PaymentOut.model_rebuild()
