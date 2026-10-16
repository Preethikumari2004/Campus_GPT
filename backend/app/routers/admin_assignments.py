from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import require_role
from ..schemas import AssignmentCreate, AssignmentUpdate, BulkAssignmentCreate, BulkIds, StudentSubjectEnrollmentCreate
from typing import Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy import bindparam, text

router = APIRouter()


@router.get("/admin/assignments")
def list_faculty_assignments(
    subject_id: int | None = None,
    faculty_id: int | None = None,
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    clauses, params = [], {"limit": limit, "offset": offset}
    if subject_id is not None:
        clauses.append("a.subject_id = :subject_id")
        params["subject_id"] = subject_id
    if faculty_id is not None:
        clauses.append("a.faculty_user_id = :faculty_id")
        params["faculty_id"] = faculty_id
    if search and search.strip():
        clauses.append("(u.full_name ILIKE :search OR u.username ILIKE :search OR s.name ILIKE :search OR s.code ILIKE :search)")
        params["search"] = f"%{search.strip()}%"
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with engine.connect() as connection:
        total = connection.execute(text(f"""
            SELECT COUNT(*) FROM faculty_subject_assignments a
            JOIN users u ON u.id = a.faculty_user_id
            JOIN subjects s ON s.id = a.subject_id{where}
        """), params).scalar_one()
        rows = connection.execute(text("""
            SELECT a.id, a.faculty_user_id AS faculty_id, u.full_name AS faculty_name,
                   u.username, a.subject_id, s.name AS subject_name, s.code AS subject_code,
                   s.semester, s.term, s.section, a.created_at
            FROM faculty_subject_assignments a
            JOIN users u ON u.id = a.faculty_user_id
            JOIN subjects s ON s.id = a.subject_id
        """ + where + " ORDER BY s.name, u.full_name LIMIT :limit OFFSET :offset"), params).mappings().all()
    return {"assignments": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@router.post("/admin/assignments", status_code=201)
def create_faculty_assignment(
    item: AssignmentCreate,
    admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            faculty_exists = connection.execute(text("SELECT 1 FROM users WHERE id = :id AND role = 'faculty'"), {"id": item.faculty_id}).scalar_one_or_none()
            if not faculty_exists:
                raise HTTPException(status_code=422, detail="Choose an existing faculty account.")
            subject_exists = connection.execute(text("SELECT 1 FROM subjects WHERE id = :id"), {"id": item.subject_id}).scalar_one_or_none()
            if not subject_exists:
                raise HTTPException(status_code=422, detail="Choose an existing subject.")
            row = connection.execute(text("""
                INSERT INTO faculty_subject_assignments (faculty_user_id, subject_id, assigned_by)
                VALUES (:faculty_id, :subject_id, :admin_id)
                RETURNING id, faculty_user_id AS faculty_id, subject_id, assigned_by, created_at
            """), {"faculty_id": item.faculty_id, "subject_id": item.subject_id, "admin_id": admin["id"]}).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That faculty member is already assigned to this subject.") from error
    return dict(row)

@router.post("/admin/assignments/bulk", status_code=201)
def create_faculty_assignments_bulk(
    selection: BulkAssignmentCreate,
    admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, int]:
    pairs = [(item.faculty_id, item.subject_id) for item in selection.assignments]
    if len(set(pairs)) != len(pairs):
        raise HTTPException(status_code=422, detail="The selection contains duplicate faculty and subject pairs.")
    faculty_ids = list({faculty_id for faculty_id, _ in pairs})
    subject_ids = list({subject_id for _, subject_id in pairs})
    try:
        with engine.begin() as connection:
            found_faculty = set(connection.execute(text("""
                SELECT id FROM users WHERE role = 'faculty' AND id IN :ids
            """).bindparams(bindparam("ids", expanding=True)), {"ids": faculty_ids}).scalars().all())
            found_subjects = set(connection.execute(text("""
                SELECT id FROM subjects WHERE id IN :ids
            """).bindparams(bindparam("ids", expanding=True)), {"ids": subject_ids}).scalars().all())
            if found_faculty != set(faculty_ids):
                raise HTTPException(status_code=422, detail="Every selected faculty member must be an existing faculty account.")
            if found_subjects != set(subject_ids):
                raise HTTPException(status_code=422, detail="Every selected subject must exist.")
            inserted = 0
            for faculty_id, subject_id in pairs:
                connection.execute(text("""
                    INSERT INTO faculty_subject_assignments (faculty_user_id, subject_id, assigned_by)
                    VALUES (:faculty_id, :subject_id, :admin_id)
                """), {"faculty_id": faculty_id, "subject_id": subject_id, "admin_id": admin["id"]})
                inserted += 1
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="At least one selected faculty member is already assigned to that subject. No assignments were added.") from error
    return {"created_count": inserted}

@router.patch("/admin/assignments/{assignment_id}")
def update_faculty_assignment(
    assignment_id: int,
    changes: AssignmentUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Choose a faculty member or subject to update.")
    try:
        with engine.begin() as connection:
            current = connection.execute(text("SELECT faculty_user_id, subject_id FROM faculty_subject_assignments WHERE id = :id"), {"id": assignment_id}).mappings().one_or_none()
            if current is None:
                raise HTTPException(status_code=404, detail="Faculty assignment not found.")
            faculty_id = values.get("faculty_id", current["faculty_user_id"])
            subject_id = values.get("subject_id", current["subject_id"])
            is_faculty = connection.execute(text("SELECT 1 FROM users WHERE id = :id AND role = 'faculty'"), {"id": faculty_id}).scalar_one_or_none()
            is_subject = connection.execute(text("SELECT 1 FROM subjects WHERE id = :id"), {"id": subject_id}).scalar_one_or_none()
            if not is_faculty or not is_subject:
                raise HTTPException(status_code=422, detail="Choose an existing faculty account and subject.")
            row = connection.execute(text("""
                UPDATE faculty_subject_assignments
                SET faculty_user_id = :faculty_id, subject_id = :subject_id
                WHERE id = :id
                RETURNING id, faculty_user_id AS faculty_id, subject_id, assigned_by, created_at
            """), {"faculty_id": faculty_id, "subject_id": subject_id, "id": assignment_id}).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That faculty member is already assigned to this subject.") from error
    return dict(row)

@router.delete("/admin/assignments/{assignment_id}")
def delete_faculty_assignment(
    assignment_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        result = connection.execute(text("DELETE FROM faculty_subject_assignments WHERE id = :id RETURNING id"), {"id": assignment_id}).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Faculty assignment not found.")
    return {"message": "Faculty assignment removed."}

@router.delete("/admin/assignments/bulk/delete")
def delete_faculty_assignments_bulk(
    selection: BulkIds,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, int]:
    ids = list(dict.fromkeys(selection.ids))
    if len(ids) != len(selection.ids):
        raise HTTPException(status_code=422, detail="Remove duplicate IDs from the selection.")
    with engine.begin() as connection:
        deleted = connection.execute(text("DELETE FROM faculty_subject_assignments WHERE id IN :ids RETURNING id").bindparams(bindparam("ids", expanding=True)), {"ids": ids}).scalars().all()
    return {"deleted_count": len(deleted), "requested_count": len(ids)}

@router.get("/admin/enrollments")
def list_student_subject_enrollments(
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT e.id, e.student_user_id AS student_id, u.full_name AS student_name,
                   u.username, e.subject_id, s.name AS subject_name, s.code AS subject_code,
                   e.created_at
            FROM student_subject_enrollments e
            JOIN users u ON u.id = e.student_user_id
            JOIN subjects s ON s.id = e.subject_id
            ORDER BY u.full_name, s.semester, s.name
        """)).mappings().all()
    return {"enrollments": [dict(row) for row in rows]}

@router.post("/admin/enrollments", status_code=201)
def enroll_student_in_subjects(
    request: StudentSubjectEnrollmentCreate,
    admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    subject_ids = list(dict.fromkeys(request.subject_ids))
    if len(subject_ids) != len(request.subject_ids):
        raise HTTPException(status_code=422, detail="Remove duplicate subjects from the selection.")
    with engine.begin() as connection:
        is_student = connection.execute(text("SELECT 1 FROM users WHERE id = :id AND role = 'student'"), {"id": request.student_id}).scalar_one_or_none()
        if not is_student:
            raise HTTPException(status_code=404, detail="Choose an existing student account.")
        valid_subjects = connection.execute(
            text("SELECT id FROM subjects WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": subject_ids},
        ).scalars().all()
        if set(valid_subjects) != set(subject_ids):
            raise HTTPException(status_code=404, detail="One or more selected subjects do not exist.")
        inserted = []
        for subject_id in subject_ids:
            enrollment_id = connection.execute(text("""
                INSERT INTO student_subject_enrollments (student_user_id, subject_id, enrolled_by)
                VALUES (:student_id, :subject_id, :admin_id)
                ON CONFLICT (student_user_id, subject_id) DO NOTHING
                RETURNING id
            """), {"student_id": request.student_id, "subject_id": subject_id, "admin_id": admin["id"]}).scalar_one_or_none()
            if enrollment_id is not None:
                inserted.append(enrollment_id)
    return {"created_count": len(inserted), "requested_count": len(subject_ids), "message": f"Student enrolled in {len(inserted)} subject(s)."}

@router.delete("/admin/enrollments/{enrollment_id}")
def remove_student_subject_enrollment(
    enrollment_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        deleted = connection.execute(text("DELETE FROM student_subject_enrollments WHERE id = :id RETURNING id"), {"id": enrollment_id}).scalar_one_or_none()
    if deleted is None:
        raise HTTPException(status_code=404, detail="Enrollment not found.")
    return {"message": "Student removed from the subject."}
