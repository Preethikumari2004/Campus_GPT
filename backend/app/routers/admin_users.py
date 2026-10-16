from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import password_hasher, require_role
from ..schemas import FacultyCreate, FacultyUpdate, StudentCreate, StudentUpdate
from typing import Any, Literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

router = APIRouter()


@router.get("/admin/users")
def list_users(
    search: str | None = None,
    role: Literal["student", "faculty", "admin"] | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with engine.connect() as connection:
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if role:
            conditions.append("role = :role")
            params["role"] = role
        if search and search.strip():
            conditions.append("(username ILIKE :search OR email ILIKE :search OR full_name ILIKE :search)")
            params["search"] = f"%{search.strip()}%"
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = connection.execute(text(f"SELECT COUNT(*) FROM users{where}"), params).scalar_one()
        users = connection.execute(
            text(f"""
                SELECT id, username, email, full_name, role, created_at
                FROM users{where}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """)
            , params
        ).mappings().all()
    return {"users": [dict(user) for user in users], "total": total, "limit": limit, "offset": offset}

@router.get("/admin/faculty")
def list_faculty(
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with engine.connect() as connection:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        filter_sql = ""
        if search and search.strip():
            filter_sql = " AND (username ILIKE :search OR email ILIKE :search OR full_name ILIKE :search)"
            params["search"] = f"%{search.strip()}%"
        total = connection.execute(text("SELECT COUNT(*) FROM users WHERE role = 'faculty'" + filter_sql), params).scalar_one()
        rows = connection.execute(text("""
            SELECT id, username, email, full_name, created_at
            FROM users WHERE role = 'faculty'
        """ + filter_sql + """
            ORDER BY full_name, id
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
        instructors = connection.execute(text("""
            SELECT s.instructor_name AS full_name,
                   array_agg(DISTINCT s.name ORDER BY s.name) AS subjects,
                   EXISTS (
                       SELECT 1 FROM users AS u
                       WHERE u.role = 'faculty'
                         AND LOWER(TRIM(u.full_name)) = LOWER(TRIM(s.instructor_name))
                   ) AS has_login
            FROM subjects AS s
            WHERE s.instructor_name IS NOT NULL AND TRIM(s.instructor_name) <> ''
            GROUP BY s.instructor_name
            ORDER BY s.instructor_name
        """)).mappings().all()
    return {
        "faculty": [dict(row) for row in rows],
        "course_instructors": [dict(row) for row in instructors],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/admin/faculty", status_code=201)
def create_faculty(
    faculty: FacultyCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            row = connection.execute(text("""
                INSERT INTO users (username, email, full_name, password_hash, role)
                VALUES (:username, :email, :full_name, :password_hash, 'faculty')
                RETURNING id, username, email, full_name, role, created_at
            """), {
                "username": faculty.username.strip(),
                "email": faculty.email.strip(),
                "full_name": faculty.full_name.strip(),
                "password_hash": password_hasher.hash(faculty.password),
            }).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username or email is already registered.") from error
    return dict(row)

@router.patch("/admin/faculty/{faculty_id}")
def update_faculty(
    faculty_id: int,
    changes: FacultyUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Enter at least one field to update.")
    values = {key: value.strip() if value is not None else value for key, value in values.items()}
    fields = ", ".join(f"{key} = :{key}" for key in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE users SET {fields}
                WHERE id = :faculty_id AND role = 'faculty'
                RETURNING id, username, email, full_name, role, created_at
            """), {**values, "faculty_id": faculty_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username or email is already in use.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Faculty account not found.")
    return dict(row)

@router.delete("/admin/faculty/{faculty_id}")
def delete_faculty(
    faculty_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    try:
        with engine.begin() as connection:
            deleted_id = connection.execute(text("""
                DELETE FROM users WHERE id = :faculty_id AND role = 'faculty'
                RETURNING id
            """), {"faculty_id": faculty_id}).scalar_one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="This faculty account is linked to existing records and cannot be removed yet.") from error
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Faculty account not found.")
    return {"message": "Faculty account removed."}

@router.get("/admin/students")
def list_students_admin(
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    where, params = "role = 'student'", {"limit": limit, "offset": offset}
    if search and search.strip():
        where += " AND (username ILIKE :search OR email ILIKE :search OR full_name ILIKE :search)"
        params["search"] = f"%{search.strip()}%"
    with engine.connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM users WHERE {where}"), params).scalar_one()
        rows = connection.execute(text(f"""
            SELECT id, username, email, full_name, role, created_at
            FROM users WHERE {where} ORDER BY full_name, id LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"students": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@router.post("/admin/students", status_code=201)
def create_student(
    item: StudentCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            row = connection.execute(text("""
                INSERT INTO users (username, email, full_name, password_hash, role)
                VALUES (:username, :email, :full_name, :password_hash, 'student')
                RETURNING id, username, email, full_name, role, created_at
            """), {
                "username": item.username.strip(), "email": item.email.strip(),
                "full_name": item.full_name.strip(), "password_hash": password_hasher.hash(item.password),
            }).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username or email is already registered.") from error
    return dict(row)

@router.patch("/admin/students/{student_id}")
def update_student(
    student_id: int,
    changes: StudentUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Enter at least one field to update.")
    values = {key: value.strip() if value else value for key, value in values.items()}
    assignments = ", ".join(f"{key} = :{key}" for key in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE users SET {assignments}
                WHERE id = :student_id AND role = 'student'
                RETURNING id, username, email, full_name, role, created_at
            """), {**values, "student_id": student_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username or email is already in use.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Student account not found.")
    return dict(row)

@router.delete("/admin/students/{student_id}")
def delete_student(
    student_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    try:
        with engine.begin() as connection:
            deleted_id = connection.execute(text("DELETE FROM users WHERE id = :id AND role = 'student' RETURNING id"), {"id": student_id}).scalar_one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="This student has attendance history. Keep the record until attendance data can be safely archived.") from error
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Student account not found.")
    return {"message": "Student account removed."}
