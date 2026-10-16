from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..database import engine
from ..security import get_current_user, require_role
from ..schemas import ClassAssignmentCreate, ClassAssignmentReview, ClassAssignmentSubmissionCreate
from ..config import ASSIGNMENT_ATTACHMENT_SUFFIXES, ASSIGNMENT_SUBMISSION_DIR, MAX_ASSIGNMENT_ATTACHMENT_BYTES
from typing import Any
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import text
from uuid import uuid4

router = APIRouter()


@router.get("/faculty/assignments")
def list_faculty_class_assignments(
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT a.id, a.subject_id, s.name AS subject_name, s.code AS subject_code,
                   a.title, a.instructions, a.due_at, a.created_at,
                   COUNT(sub.id)::int AS submission_count,
                   COUNT(sub.id) FILTER (WHERE sub.reviewed_at IS NOT NULL)::int AS reviewed_count
            FROM course_assignments a
            JOIN subjects s ON s.id = a.subject_id
            LEFT JOIN assignment_submissions sub ON sub.assignment_id = a.id
            WHERE a.faculty_user_id = :faculty_id
            GROUP BY a.id, s.id
            ORDER BY a.due_at, a.created_at DESC
        """), {"faculty_id": faculty["id"]}).mappings().all()
    return {"assignments": [dict(row) for row in rows]}

@router.post("/faculty/assignments", status_code=201)
def create_faculty_class_assignment(
    assignment: ClassAssignmentCreate,
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, Any]:
    with engine.begin() as connection:
        subject = connection.execute(text("""
            SELECT s.id, s.name, s.code
            FROM subjects s
            JOIN faculty_subject_assignments a ON a.subject_id = s.id
            WHERE s.id = :subject_id AND a.faculty_user_id = :faculty_id
        """), {"subject_id": assignment.subject_id, "faculty_id": faculty["id"]}).mappings().one_or_none()
        if subject is None:
            raise HTTPException(status_code=403, detail="You can create assignments only for a subject assigned to you.")
        row = connection.execute(text("""
            INSERT INTO course_assignments (subject_id, faculty_user_id, title, instructions, due_at)
            VALUES (:subject_id, :faculty_id, :title, :instructions, :due_at)
            RETURNING id, subject_id, title, instructions, due_at, created_at
        """), {
            "subject_id": assignment.subject_id,
            "faculty_id": faculty["id"],
            "title": assignment.title.strip(),
            "instructions": assignment.instructions.strip(),
            "due_at": assignment.due_at,
        }).mappings().one()
    return {**dict(row), "subject_name": subject["name"], "subject_code": subject["code"], "submission_count": 0, "reviewed_count": 0}

@router.get("/faculty/assignments/{assignment_id}/submissions")
def list_assignment_submissions(
    assignment_id: int,
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        assignment = connection.execute(text("""
            SELECT id FROM course_assignments
            WHERE id = :assignment_id AND faculty_user_id = :faculty_id
        """), {"assignment_id": assignment_id, "faculty_id": faculty["id"]}).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(status_code=404, detail="Assignment not found for your account.")
        rows = connection.execute(text("""
            SELECT sub.id, sub.student_user_id, u.full_name AS student_name,
                   u.username, sub.response_text, sub.submitted_at,
                   sub.score, sub.feedback, sub.reviewed_at, sub.attachment_name
            FROM assignment_submissions sub
            JOIN users u ON u.id = sub.student_user_id
            WHERE sub.assignment_id = :assignment_id
            ORDER BY sub.submitted_at, u.full_name
        """), {"assignment_id": assignment_id}).mappings().all()
    return {"submissions": [dict(row) for row in rows]}

@router.patch("/faculty/assignments/{assignment_id}/submissions/{submission_id}")
def review_assignment_submission(
    assignment_id: int,
    submission_id: int,
    review: ClassAssignmentReview,
    faculty: dict[str, Any] = Depends(require_role("faculty")),
) -> dict[str, Any]:
    with engine.begin() as connection:
        row = connection.execute(text("""
            UPDATE assignment_submissions sub
            SET score = :score, feedback = :feedback, reviewed_at = NOW()
            FROM course_assignments a
            WHERE sub.id = :submission_id
              AND sub.assignment_id = :assignment_id
              AND a.id = sub.assignment_id
              AND a.faculty_user_id = :faculty_id
            RETURNING sub.id, sub.score, sub.feedback, sub.reviewed_at
        """), {
            "submission_id": submission_id,
            "assignment_id": assignment_id,
            "faculty_id": faculty["id"],
            "score": review.score,
            "feedback": review.feedback.strip() if review.feedback else None,
        }).mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Submission not found for your assignment.")
    return dict(row)

@router.get("/student/assignments")
def list_student_class_assignments(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT a.id, a.subject_id, s.name AS subject_name, s.code AS subject_code,
                   a.title, a.instructions, a.due_at, a.created_at,
                   sub.id AS submission_id, sub.response_text, sub.submitted_at,
                   sub.score, sub.feedback, sub.reviewed_at, sub.attachment_name
            FROM student_subject_enrollments e
            JOIN subjects s ON s.id = e.subject_id
            JOIN course_assignments a ON a.subject_id = e.subject_id
            LEFT JOIN assignment_submissions sub
              ON sub.assignment_id = a.id AND sub.student_user_id = e.student_user_id
            WHERE e.student_user_id = :student_id
            ORDER BY a.due_at, a.created_at DESC
        """), {"student_id": student["id"]}).mappings().all()
    return {"assignments": [dict(row) for row in rows]}

@router.post("/student/assignments/{assignment_id}/submit")
def submit_class_assignment(
    assignment_id: int,
    submission: ClassAssignmentSubmissionCreate,
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    response_text = submission.response_text.strip()
    if not response_text:
        raise HTTPException(status_code=422, detail="Enter a response or attach a file before submitting.")
    with engine.begin() as connection:
        enrolled = connection.execute(text("""
            SELECT a.id FROM course_assignments a
            JOIN student_subject_enrollments e ON e.subject_id = a.subject_id
            WHERE a.id = :assignment_id AND e.student_user_id = :student_id
        """), {"assignment_id": assignment_id, "student_id": student["id"]}).scalar_one_or_none()
        if enrolled is None:
            raise HTTPException(status_code=403, detail="You can submit only assignments for your enrolled subjects.")
        row = connection.execute(text("""
            INSERT INTO assignment_submissions (assignment_id, student_user_id, response_text)
            VALUES (:assignment_id, :student_id, :response_text)
            ON CONFLICT (assignment_id, student_user_id)
            DO UPDATE SET response_text = EXCLUDED.response_text,
                          submitted_at = NOW(), score = NULL,
                          feedback = NULL, reviewed_at = NULL
            RETURNING id, assignment_id, response_text, submitted_at, score, feedback, reviewed_at
        """), {
            "assignment_id": assignment_id,
            "student_id": student["id"],
            "response_text": response_text,
        }).mappings().one()
    return dict(row)

@router.post("/student/assignments/{assignment_id}/submit-file")
async def submit_class_assignment_file(
    assignment_id: int,
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    response_text: str = Query(default="", max_length=20000),
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    safe_filename = Path(filename.replace("\\", "/")).name
    suffix = Path(safe_filename).suffix.lower()
    if not safe_filename or suffix not in ASSIGNMENT_ATTACHMENT_SUFFIXES:
        raise HTTPException(status_code=415, detail="Use a PDF, Word, text, code, image, or ZIP attachment.")

    file_bytes = bytearray()
    async for chunk in request.stream():
        file_bytes.extend(chunk)
        if len(file_bytes) > MAX_ASSIGNMENT_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Assignment attachments must be 10 MB or smaller.")
    if not file_bytes and not response_text.strip():
        raise HTTPException(status_code=422, detail="Enter a response or attach a non-empty file before submitting.")

    attachment_key = f"{uuid4().hex}{suffix}"
    destination = ASSIGNMENT_SUBMISSION_DIR / attachment_key
    old_attachment_key = None
    try:
        with engine.begin() as connection:
            enrolled = connection.execute(text("""
                SELECT a.id
                FROM course_assignments a
                JOIN student_subject_enrollments e ON e.subject_id = a.subject_id
                WHERE a.id = :assignment_id AND e.student_user_id = :student_id
            """), {"assignment_id": assignment_id, "student_id": student["id"]}).scalar_one_or_none()
            if enrolled is None:
                raise HTTPException(status_code=403, detail="You can submit only assignments for your enrolled subjects.")

            old_attachment_key = connection.execute(text("""
                SELECT attachment_key FROM assignment_submissions
                WHERE assignment_id = :assignment_id AND student_user_id = :student_id
            """), {"assignment_id": assignment_id, "student_id": student["id"]}).scalar_one_or_none()

            ASSIGNMENT_SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
            if file_bytes:
                destination.write_bytes(file_bytes)
            row = connection.execute(text("""
                INSERT INTO assignment_submissions
                    (assignment_id, student_user_id, response_text, attachment_name, attachment_key)
                VALUES (:assignment_id, :student_id, :response_text, :attachment_name, :attachment_key)
                ON CONFLICT (assignment_id, student_user_id)
                DO UPDATE SET response_text = EXCLUDED.response_text,
                              submitted_at = NOW(), score = NULL, feedback = NULL, reviewed_at = NULL,
                              attachment_name = COALESCE(EXCLUDED.attachment_name, assignment_submissions.attachment_name),
                              attachment_key = COALESCE(EXCLUDED.attachment_key, assignment_submissions.attachment_key)
                RETURNING id, assignment_id, response_text, submitted_at, score, feedback,
                          reviewed_at, attachment_name
            """), {
                "assignment_id": assignment_id,
                "student_id": student["id"],
                "response_text": response_text.strip(),
                "attachment_name": safe_filename if file_bytes else None,
                "attachment_key": attachment_key if file_bytes else None,
            }).mappings().one()
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if old_attachment_key and file_bytes and old_attachment_key != attachment_key:
        (ASSIGNMENT_SUBMISSION_DIR / Path(old_attachment_key).name).unlink(missing_ok=True)
    return dict(row)

@router.get("/assignments/submissions/{submission_id}/attachment")
def download_assignment_attachment(
    submission_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    if current_user["role"] not in {"student", "faculty"}:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    with engine.connect() as connection:
        row = connection.execute(text("""
            SELECT sub.attachment_key, sub.attachment_name
            FROM assignment_submissions sub
            JOIN course_assignments a ON a.id = sub.assignment_id
            WHERE sub.id = :submission_id AND sub.attachment_key IS NOT NULL
              AND ((:role = 'student' AND sub.student_user_id = :user_id)
                OR (:role = 'faculty' AND a.faculty_user_id = :user_id))
        """), {
            "submission_id": submission_id,
            "role": current_user["role"],
            "user_id": current_user["id"],
        }).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    storage_key = Path(row["attachment_key"]).name
    path = (ASSIGNMENT_SUBMISSION_DIR / storage_key).resolve()
    if path.parent != ASSIGNMENT_SUBMISSION_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is unavailable.")
    return FileResponse(path, media_type="application/octet-stream", filename=row["attachment_name"])
