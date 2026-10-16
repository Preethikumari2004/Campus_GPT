from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import password_hasher, require_role
from ..schemas import FacultyProfileUpdate
from typing import Any, Literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

router = APIRouter()


@router.get("/faculty/profile")
def read_faculty_profile(
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, Any]:
    return {key: faculty[key] for key in ("id", "username", "email", "full_name", "role")}

def update_account_profile(
    changes: FacultyProfileUpdate,
    account: dict[str, Any],
    role: Literal["student", "faculty"],
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    current_password = values.pop("current_password", None)
    new_password = values.pop("new_password", None)
    if bool(current_password) != bool(new_password):
        raise HTTPException(status_code=400, detail="Enter both your current and new password to change your password.")

    if "full_name" in values:
        values["full_name"] = values["full_name"].strip() if values["full_name"] else ""
        if not values["full_name"]:
            raise HTTPException(status_code=422, detail="Full name cannot be blank.")
    if "email" in values:
        values["email"] = values["email"].strip().lower() if values["email"] else ""
        if not values["email"]:
            raise HTTPException(status_code=422, detail="Email cannot be blank.")
    if new_password:
        with engine.connect() as connection:
            password_hash = connection.execute(
                text("SELECT password_hash FROM users WHERE id = :user_id AND role = :role"),
                {"user_id": account["id"], "role": role},
            ).scalar_one_or_none()
        if password_hash is None or not password_hasher.verify(current_password, password_hash):
            raise HTTPException(status_code=400, detail="Your current password is incorrect.")
        values["password_hash"] = password_hasher.hash(new_password)

    if not values:
        raise HTTPException(status_code=400, detail="Make a profile change before saving.")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE users SET {assignments}
                WHERE id = :user_id AND role = :role
                RETURNING id, username, email, full_name, role
            """), {**values, "user_id": account["id"], "role": role}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That email address is already used by another account.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Account was not found.")
    return dict(row)

@router.patch("/faculty/profile")
def update_faculty_profile(
    changes: FacultyProfileUpdate,
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, Any]:
    return update_account_profile(changes, faculty, "faculty")

@router.get("/student/profile")
def read_student_profile(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    return {key: student[key] for key in ("id", "username", "email", "full_name", "role")}

@router.patch("/student/profile")
def update_student_profile(
    changes: FacultyProfileUpdate,
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    return update_account_profile(changes, student, "student")
