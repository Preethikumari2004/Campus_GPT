from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from ..database import engine
from ..security import require_role
from ..schemas import AttendanceCreate
from typing import Any
from sqlalchemy import bindparam, text

router = APIRouter()


@router.post("/attendance/sessions", status_code=201)
def create_attendance_session(
    attendance: AttendanceCreate,
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, Any]:
    student_ids = [entry.student_id for entry in attendance.records]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=422, detail="A student can appear only once in an attendance session.")

    with engine.begin() as connection:
        subject_params: dict[str, Any] = {"faculty_id": faculty["id"]}
        if attendance.subject_id is not None:
            subject_filter = "s.id = :subject_id"
            subject_params["subject_id"] = attendance.subject_id
        elif attendance.course_name:
            subject_filter = "lower(s.name) = lower(:course_name)"
            subject_params["course_name"] = attendance.course_name.strip()
        else:
            raise HTTPException(status_code=422, detail="Choose a subject before saving attendance.")
        subject = connection.execute(text(f"""
            SELECT s.id, s.name
            FROM subjects s
            JOIN faculty_subject_assignments a ON a.subject_id = s.id
            WHERE a.faculty_user_id = :faculty_id AND {subject_filter}
            ORDER BY s.id
            LIMIT 1
        """), subject_params).mappings().one_or_none()
        if subject is None:
            raise HTTPException(status_code=403, detail="Choose a subject assigned to your faculty account.")

        # Serialize saves for this faculty, subject, and date so two quick clicks
        # cannot create duplicate sessions.
        connection.execute(text("""
            SELECT pg_advisory_xact_lock(CAST(:faculty_id AS INTEGER), hashtext(:session_key))
        """), {
            "faculty_id": faculty["id"],
            "session_key": f"{subject['id']}:{attendance.session_date.isoformat()}",
        })

        existing_students = connection.execute(
            text("SELECT id FROM users WHERE role = 'student' AND id IN :student_ids").bindparams(
                bindparam("student_ids", expanding=True)
            ),
            {"student_ids": student_ids},
        ).scalars().all()
        if set(existing_students) != set(student_ids):
            raise HTTPException(status_code=400, detail="One or more selected accounts are not students.")

        enrolled_students = connection.execute(
            text("""
                SELECT DISTINCT e.student_user_id
                FROM student_subject_enrollments e
                JOIN faculty_subject_assignments a ON a.subject_id = e.subject_id
                WHERE a.faculty_user_id = :faculty_id AND e.subject_id = :subject_id
                  AND e.student_user_id IN :student_ids
            """).bindparams(bindparam("student_ids", expanding=True)),
            {"faculty_id": faculty["id"], "subject_id": subject["id"], "student_ids": student_ids},
        ).scalars().all()
        if set(enrolled_students) != set(student_ids):
            raise HTTPException(status_code=403, detail="You can only record attendance for students enrolled in this subject.")

        existing_session = connection.execute(text("""
            SELECT id FROM attendance_sessions
            WHERE created_by = :faculty_id AND session_date = :session_date
              AND (subject_id = :subject_id OR (subject_id IS NULL AND lower(course_name) = lower(:course_name)))
            ORDER BY id
            LIMIT 1
            FOR UPDATE
        """), {
            "faculty_id": faculty["id"],
            "session_date": attendance.session_date,
            "subject_id": subject["id"],
            "course_name": subject["name"],
        }).scalar_one_or_none()
        replaced_existing = existing_session is not None
        if existing_session is None:
            session_id = connection.execute(
                text("""
                    INSERT INTO attendance_sessions (subject_id, course_name, session_date, created_by)
                    VALUES (:subject_id, :course_name, :session_date, :created_by)
                    RETURNING id
                """),
                {
                    "subject_id": subject["id"],
                    "course_name": subject["name"],
                    "session_date": attendance.session_date,
                    "created_by": faculty["id"],
                },
            ).scalar_one()
        else:
            session_id = existing_session
            connection.execute(text("""
                UPDATE attendance_sessions SET subject_id = :subject_id, course_name = :course_name
                WHERE id = :session_id
            """), {"subject_id": subject["id"], "course_name": subject["name"], "session_id": session_id})
            connection.execute(text("DELETE FROM attendance_records WHERE session_id = :session_id"), {"session_id": session_id})
        connection.execute(
            text("""
                INSERT INTO attendance_records (session_id, student_id, status)
                VALUES (:session_id, :student_id, :status)
            """),
            [
                {"session_id": session_id, "student_id": entry.student_id, "status": entry.status}
                for entry in attendance.records
            ],
        )

    return {
        "message": "Attendance saved.",
        "session_id": session_id,
        "course_name": subject["name"],
        "session_date": attendance.session_date.isoformat(),
        "students_recorded": len(student_ids),
        "replaced_existing": replaced_existing,
    }

@router.get("/faculty/attendance")
def list_faculty_attendance(
    subject_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.subject_id, COALESCE(subject.name, s.course_name) AS subject_name,
                   s.session_date,
                   COUNT(DISTINCT s.id)::int AS sessions_recorded,
                   COUNT(r.id)::int AS students_recorded,
                   COUNT(r.id) FILTER (WHERE r.status = 'present')::int AS present_count,
                   COUNT(r.id) FILTER (WHERE r.status = 'absent')::int AS absent_count
            FROM attendance_sessions s
            LEFT JOIN subjects subject ON subject.id = s.subject_id
            LEFT JOIN attendance_records r ON r.session_id = s.id
            WHERE s.created_by = :faculty_id
              AND (:subject_id IS NULL OR s.subject_id = :subject_id)
            GROUP BY s.subject_id, COALESCE(subject.name, s.course_name), s.session_date
            ORDER BY s.session_date DESC, subject_name
            LIMIT :limit
        """), {"faculty_id": faculty["id"], "subject_id": subject_id, "limit": limit}).mappings().all()
    return {"sessions": [dict(row) for row in rows]}

@router.get("/attendance/me")
def read_my_attendance(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT s.id AS session_id, s.course_name, s.session_date, r.status
                FROM attendance_records AS r
                JOIN attendance_sessions AS s ON s.id = r.session_id
                WHERE r.student_id = :student_id
                ORDER BY s.session_date DESC, s.id DESC
            """),
            {"student_id": student["id"]},
        ).mappings().all()

    present_count = sum(1 for row in rows if row["status"] == "present")
    total_count = len(rows)
    return {
        "present": present_count,
        "total": total_count,
        "percentage": round((present_count / total_count) * 100, 1) if total_count else 0,
        "records": [
            {
                "session_id": row["session_id"],
                "course_name": row["course_name"],
                "session_date": row["session_date"].isoformat(),
                "status": row["status"],
            }
            for row in rows
        ],
    }
