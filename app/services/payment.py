"""Core payment logic - the production version of process_payment() from the FinPay doc.

Rules (Part C prompt + Part B/D decisions):
  1. payer, payee and payment_request must be present
  2. payer must be an active user; payee must be active (merchant must be authorized)
  3. amount must be a number, > 0, within limits, max 2 decimals, currency must match
  4. a payment_request_id may be processed only once per payer (duplicate -> rejected)
  5. wallet must have enough balance
  6. debit + credit + transaction record happen in ONE database transaction;
     any failure rolls everything back
The function never raises; it always returns a PaymentResult.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Account, Role, Transaction
from ..money import parse_amount, to_minor

log = logging.getLogger("finpay.payment")


@dataclass
class PaymentResult:
    success: bool
    reason: str
    code: str = "OK"  # machine-readable, used for HTTP status mapping
    transaction: Transaction | None = None


def _reject(code: str, reason: str) -> PaymentResult:
    return PaymentResult(False, reason, code)


def process_payment(db: Session, payer: Account | None, payee: Account | None, payment_request) -> PaymentResult:
    try:
        # --- missing / null inputs ---
        if payer is None or payee is None or payment_request is None:
            return _reject("INVALID_INPUT", "Payer, payee and payment request are required.")
        request_id = getattr(payment_request, "payment_request_id", None)
        if not request_id:
            return _reject("INVALID_INPUT", "payment_request_id is required.")

        # --- who is allowed to pay / be paid (FR1, FR2, FR4) ---
        if not payer.is_active or payer.role != Role.user.value:
            return _reject("FORBIDDEN", "Payer must be an active user.")
        if payer.id == payee.id:
            return _reject("INVALID_INPUT", "You cannot pay yourself.")
        if not payee.is_active or payee.role not in (Role.user.value, Role.merchant.value):
            return _reject("PAYEE_NOT_ALLOWED", "Recipient account is not active.")
        if payee.role == Role.merchant.value and not payee.is_authorized:
            return _reject("PAYEE_NOT_ALLOWED", "Merchant is not authorized to receive payments.")

        # --- amount rules ---
        amount = parse_amount(payment_request.amount)
        if amount is None:
            return _reject("INVALID_AMOUNT", "Payment amount is missing or not a valid number.")
        if amount <= 0:
            return _reject("INVALID_AMOUNT", "Payment amount must be greater than 0.")
        if amount.as_tuple().exponent < -2:
            return _reject("INVALID_AMOUNT", "Payment amount can have at most 2 decimal places.")
        if amount < settings.min_payment:
            return _reject("INVALID_AMOUNT", f"Minimum payment amount is {settings.min_payment}.")
        if amount > settings.max_payment:
            return _reject("INVALID_AMOUNT", f"Maximum payment amount is {settings.max_payment}.")
        currency = (payment_request.currency or settings.currency).upper()
        if currency != settings.currency or payer.currency != payee.currency:
            return _reject("INVALID_CURRENCY", f"Only {settings.currency} payments are supported.")
        amount_minor = to_minor(amount)

        # --- duplicate request (checked before balance so retries get a stable answer) ---
        exists = db.scalar(
            select(Transaction.id).where(
                Transaction.payer_id == payer.id, Transaction.payment_request_id == request_id
            )
        )
        if exists:
            return _reject("DUPLICATE", "Payment request already processed.")

        # --- balance check ---
        if payer.balance_minor < amount_minor:
            return _reject("INSUFFICIENT_FUNDS", "Insufficient wallet balance.")

        # --- atomic debit / credit / record ---
        debited = db.execute(
            update(Account)
            .where(Account.id == payer.id, Account.balance_minor >= amount_minor)
            .values(balance_minor=Account.balance_minor - amount_minor)
        )
        if debited.rowcount != 1:  # lost a race with another payment
            db.rollback()
            return _reject("INSUFFICIENT_FUNDS", "Insufficient wallet balance.")
        db.execute(
            update(Account).where(Account.id == payee.id).values(balance_minor=Account.balance_minor + amount_minor)
        )
        txn = Transaction(
            payment_request_id=request_id,
            payer_id=payer.id,
            payee_id=payee.id,
            amount_minor=amount_minor,
            currency=currency,
            status="SUCCESS",
            description=payment_request.description,
        )
        db.add(txn)
        db.commit()  # everything or nothing
        db.refresh(payer)
        db.refresh(payee)
        return PaymentResult(True, "Payment processed successfully.", "OK", txn)

    except IntegrityError:
        db.rollback()
        return _reject("DUPLICATE", "Payment request already processed.")
    except Exception:  # never raise; roll back every change
        db.rollback()
        log.exception("Payment failed unexpectedly")
        return _reject("INTERNAL_ERROR", "Payment failed. All changes were rolled back.")
