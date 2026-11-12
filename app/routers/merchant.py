from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_merchant
from ..models import Account, Transaction
from ..schemas import TransactionOut
from .payments import to_out

router = APIRouter(prefix="/merchant", tags=["Merchant"])


@router.get("/transactions", response_model=list[TransactionOut])  # FR4: authorized merchants only
def received_payments(
    merchant: Account = Depends(require_merchant),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.payee_id == merchant.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [to_out(t) for t in rows]
