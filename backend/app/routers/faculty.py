from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import require_role
from typing import Any
from sqlalchemy import text

router = APIRouter()


@router.get("/faculty/students")
def list_students(
    subject_id: int | None = None,
    _faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, list[dict[str, Any]]]:
    subject_filter = ""
    params: dict[str, Any] = {"faculty_id": _faculty["id"]}
    if subject_id is not None:
        subject_filter = " AND e.subject_id = :subject_id"
        params["subject_id"] = subject_id
    with engine.connect() as connection:
        if subject_id is not None:
            assigned_subject = connection.execute(text("""
                SELECT 1 FROM faculty_subject_assignments
                WHERE faculty_user_id = :faculty_id AND subject_id = :subject_id
            """), params).scalar_one_or_none()
            if assigned_subject is None:
                raise HTTPException(status_code=403, detail="Choose a subject assigned to your faculty account.")
        students = connection.execute(
            text(f"""
                SELECT DISTINCT u.id, u.username, u.full_name
                FROM users u
                JOIN student_subject_enrollments e ON e.student_user_id = u.id
                JOIN faculty_subject_assignments a ON a.subject_id = e.subject_id
                WHERE u.role = 'student' AND a.faculty_user_id = :faculty_id
                  {subject_filter}
                ORDER BY u.full_name, u.id
            """), params,
        ).mappings().all()
    return {"students": [dict(student) for student in students]}

@router.get("/faculty/subjects")
def list_faculty_subjects(
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.id, s.course_id, c.name AS course_name,
                   s.name, s.code, s.semester, s.term, s.section,
                   s.specialization_id, p.name AS specialization_name
            FROM faculty_subject_assignments a
            JOIN subjects s ON s.id = a.subject_id
            LEFT JOIN courses c ON c.id = s.course_id
            LEFT JOIN specializations p ON p.id = s.specialization_id
            WHERE a.faculty_user_id = :faculty_id ORDER BY s.semester, s.name
        """), {"faculty_id": faculty["id"]}).mappings().all()
    return {"subjects": [dict(row) for row in rows]}
