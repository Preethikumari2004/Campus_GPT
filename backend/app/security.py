from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import text
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from .config import JWT_ALGORITHM, JWT_SECRET_KEY
from .database import engine, password_hasher

bearer_scheme = HTTPBearer()


def create_access_token(user_id: int, role: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid login token") from error

    with engine.connect() as connection:
        user = connection.execute(
            text("""
                SELECT id, username, email, full_name, role
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).mappings().one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="User account not found")

    return dict(user)

def require_role(required_role: str):
    def role_dependency(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if current_user["role"] != required_role:
            raise HTTPException(status_code=403, detail="Access denied")
        return current_user

    return role_dependency
