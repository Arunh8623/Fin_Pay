from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_payment_operator
from ..models import Account
from ..money import from_minor, parse_amount, to_minor
from ..schemas import BalanceOut, TopUpRequest

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get("/balance", response_model=BalanceOut)  # FR3
def balance(account: Account = Depends(require_payment_operator), db: Session = Depends(get_db)):
    db.refresh(account)
    return BalanceOut(balance=from_minor(account.balance_minor), currency=account.currency)


@router.post("/topup", response_model=BalanceOut)
def topup(body: TopUpRequest, account: Account = Depends(require_payment_operator), db: Session = Depends(get_db)):
    """Demo top-up so you can test payments. In production this would be a bank/UPI/card gateway."""
    amount = parse_amount(body.amount)
    if amount is None or amount <= 0 or amount.as_tuple().exponent < -2 or amount > settings.max_topup:
        raise HTTPException(422, f"Amount must be > 0, max 2 decimals and at most {settings.max_topup}")
    db.execute(
        update(Account).where(Account.id == account.id).values(balance_minor=Account.balance_minor + to_minor(amount))
    )
    db.commit()
    db.refresh(account)
    return BalanceOut(balance=from_minor(account.balance_minor), currency=account.currency)
