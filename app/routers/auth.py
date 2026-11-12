from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_account
from ..models import Account, Role
from ..schemas import AccountOut, RegisterRequest, TokenResponse
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["Authentication"])


@router.post("/auth/register", response_model=AccountOut, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(Account.id).where(Account.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    account = Account(
        email=email,
        full_name=body.full_name,
        business_name=body.business_name if body.role == "merchant" else None,
        password_hash=hash_password(body.password),
        role=body.role,
        is_authorized=body.role == "user",  # merchants wait for admin approval
        currency=settings.currency,
    )
    db.add(account)
    db.commit()
    return account


@router.post("/auth/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    account = db.scalar(select(Account).where(Account.email == form.username.lower()))
    if not account or not account.is_active or not verify_password(form.password, account.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    return TokenResponse(access_token=create_access_token(account.id, account.role))


@router.get("/users/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)):
    return account
