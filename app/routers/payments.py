from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_payment_operator, require_user
from ..models import Account, Transaction
from ..money import from_minor
from ..schemas import PaymentOut, PaymentRequestIn, TransactionOut
from ..services.payment import process_payment

router = APIRouter(prefix="/payments", tags=["Payments"])

STATUS_BY_CODE = {
    "INVALID_INPUT": 422,
    "INVALID_AMOUNT": 422,
    "INVALID_CURRENCY": 422,
    "INSUFFICIENT_FUNDS": 402,
    "DUPLICATE": 409,
    "PAYEE_NOT_ALLOWED": 403,
    "FORBIDDEN": 403,
    "INTERNAL_ERROR": 500,
}


def to_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        payment_request_id=t.payment_request_id,
        payer_id=t.payer_id,
        payee_id=t.payee_id,
        amount=from_minor(t.amount_minor),
        currency=t.currency,
        status=t.status,
        description=t.description,
        created_at=t.created_at,
    )


@router.post("", response_model=PaymentOut, status_code=201)  # FR2
def make_payment(body: PaymentRequestIn, payer: Account = Depends(require_user), db: Session = Depends(get_db)):
    payee = db.get(Account, body.payee_id)
    result = process_payment(db, payer, payee, body)
    if not result.success:
        return JSONResponse(
            status_code=STATUS_BY_CODE.get(result.code, 400),
            content={"success": False, "reason": result.reason, "transaction": None},
        )
    return PaymentOut(success=True, reason=result.reason, transaction=to_out(result.transaction))


@router.get("", response_model=list[TransactionOut])
def history(
    account: Account = Depends(require_payment_operator),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = db.scalars(
        select(Transaction)
        .where(or_(Transaction.payer_id == account.id, Transaction.payee_id == account.id))
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [to_out(t) for t in rows]


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: str, account: Account = Depends(require_payment_operator), db: Session = Depends(get_db)):
    t = db.get(Transaction, transaction_id)
    if not t or account.id not in (t.payer_id, t.payee_id):
        raise HTTPException(404, "Transaction not found")
    return to_out(t)
