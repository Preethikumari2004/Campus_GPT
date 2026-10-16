from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Header
from ..database import engine
from ..security import create_access_token, get_current_user, password_hasher
from ..schemas import AccountCreate, LoginRequest, TokenResponse
from typing import Any
from sqlalchemy.exc import IntegrityError
from hmac import compare_digest
import os
from sqlalchemy import text

router = APIRouter()


@router.post("/auth/register", status_code=201)
def register_account(
    account: AccountCreate,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key or not compare_digest(x_admin_key or "", admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    password_hash = password_hasher.hash(account.password)

    try:
        with engine.begin() as connection:
            user = connection.execute(
                text("""
                    INSERT INTO users
                        (username, email, full_name, password_hash, role)
                    VALUES
                        (:username, :email, :full_name, :password_hash, :role)
                    RETURNING id, username, email, full_name, role
                """),
                {
                    "username": account.username,
                    "email": account.email,
                    "full_name": account.full_name,
                    "password_hash": password_hash,
                    "role": account.role,
                },
            ).mappings().one()
    except IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="That username or email is already registered",
        ) from error

    return dict(user)

@router.post("/auth/login", response_model=TokenResponse)
def login(credentials: LoginRequest) -> TokenResponse:
    with engine.connect() as connection:
        user = connection.execute(
            text("""
                SELECT id, password_hash, role
                FROM users
                WHERE username = :username
            """),
            {"username": credentials.username},
        ).mappings().one_or_none()

    if user is None or not password_hasher.verify(
        credentials.password, user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    return TokenResponse(
        access_token=create_access_token(user["id"], user["role"])
    )

@router.get("/auth/me")
def read_current_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return current_user
