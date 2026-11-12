from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Account, Role
from ..schemas import AccountOut

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


def _merchant(db: Session, merchant_id: int) -> Account:
    m = db.get(Account, merchant_id)
    if not m or m.role != Role.merchant.value:
        raise HTTPException(404, "Merchant not found")
    return m


@router.get("/merchants", response_model=list[AccountOut])
def list_merchants(pending_only: bool = False, db: Session = Depends(get_db)):
    q = select(Account).where(Account.role == Role.merchant.value)
    if pending_only:
        q = q.where(Account.is_authorized.is_(False))
    return list(db.scalars(q.order_by(Account.id)))


@router.post("/merchants/{merchant_id}/authorize", response_model=AccountOut)
def authorize_merchant(merchant_id: int, db: Session = Depends(get_db)):
    m = _merchant(db, merchant_id)
    m.is_authorized = True
    db.commit()
    return m


@router.post("/merchants/{merchant_id}/revoke", response_model=AccountOut)
def revoke_merchant(merchant_id: int, db: Session = Depends(get_db)):
    m = _merchant(db, merchant_id)
    m.is_authorized = False
    db.commit()
    return m
