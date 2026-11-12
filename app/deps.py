import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Account, Role
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_account(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Account:
    """Authentication (FR1 / NFR5): valid token + active account."""
    err = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = decode_access_token(token)
        account = db.get(Account, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise err
    if account is None or not account.is_active:
        raise err
    return account


def require_payment_operator(account: Account = Depends(get_current_account)) -> Account:
    """Authorization (FR1 / FR4): users, or merchants approved by an admin."""
    if account.role == Role.admin.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins cannot perform payment operations")
    if account.role == Role.merchant.value and not account.is_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Merchant account is not authorized yet")
    return account


def require_user(account: Account = Depends(require_payment_operator)) -> Account:
    if account.role != Role.user.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only users can make payments")
    return account


def require_merchant(account: Account = Depends(require_payment_operator)) -> Account:
    if account.role != Role.merchant.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Merchant access only")
    return account


def require_admin(account: Account = Depends(get_current_account)) -> Account:
    if account.role != Role.admin.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access only")
    return account
