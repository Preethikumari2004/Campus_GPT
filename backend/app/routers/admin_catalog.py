from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import get_current_user, password_hasher, require_role
from ..schemas import BulkIds, CourseCreate, CourseUpdate, DepartmentCreate, DepartmentUpdate, SpecializationCreate, SpecializationUpdate, SubjectCreate, SubjectUpdate
from typing import Any, Literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy import bindparam, text
import re

router = APIRouter()


MCA_CATALOG_IMPORT = [
    ("Fall2025_MCA_I_SECB_E1CAB604", "Advanced Data Science Techniques", "Fall 2025", 1, "B", "Aman Kumar Sharma"),
    ("Fall2025_MCA_I_SECB_E1CAB605", "Advanced UI and UX Design for Developers", "Fall 2025", 1, "B", "Santosh Goyal"),
    ("Fall2025_MCA_I_SECB_E1CAB600", "Discrete Structures", "Fall 2025", 1, "B", "Naren Sathyanarayanan"),
    ("Fall2025_MCA_I_SECB_E1CAB606", "Front-End Frameworks and Technologies", "Fall 2025", 1, "B", "Veera Raghav Kathula"),
    ("Fall2025_MCA_I_SECB_E1CAB603", "Mastering Python: From Basics to Advanced", "Fall 2025", 1, "B", "Renita Joy R"),
    ("Fall2025_MCA_I_SECB_E1CAB602", "Problem solving through Aptitude - I", "Fall 2025", 1, "B", "Ajith Pandian"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB610", "Advanced Data Structures and Algorithms", "Winter 2026", 2, "B", "Lakshmi Devi S"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB607", "Applied Statistics", "Winter 2026", 2, "B", "Mahendra Babu Chennupati"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB612", "Database Design and Implementation", "Winter 2026", 2, "B", "Lenin J"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB611", "Java Object-Oriented Design and Programming", "Winter 2026", 2, "B", "Mary Agnes J"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB613", "Machine Learning Theory and Practice", "Winter 2026", 2, "B", "Tanisha Das"),
    ("ASAC_CSA_WIN26_MCA_2025_Sem2_SECB_E1CAB609", "Problem solving through Aptitude - II-MCA-B", "Winter 2026", 2, "B", "Ajith Pandian"),
    ("FALL26_ASAC_CA_MCA_SEM3_A_B_E1CAB708", "Applied Reinforcement Learning", "Fall 2026", 3, "A/B", "DEEPESH ."),
    ("FALL26_ASAC_CA_MCA_SEM3_B_E1CAB703", "Computer Networks and Communications - B Section", "Fall 2026", 3, "B", "Dr. Krishnan R"),
    ("FALL26_ASAC_CA_MCA_SEM3_A_B_E1CAB702", "Deep Learning Models and Applications", "Fall 2026", 3, "A/B", "Tanisha Das"),
    ("FALL26_ASAC_CA_MCA_SEM3_B_E1CAB704", "Engineering Principles of Software", "Fall 2026", 3, "B", "Gomathy V"),
    ("FALL26_ASAC_CA_MCA_SEM3_A_B_E1CAB707", "Generative Models and Applications", "Fall 2026", 3, "A/B", "Sanjivini Chowdhury"),
    ("FALL26_ASAC_CA_MCA_SEM3_A_B_E1CAB705", "NLP Algorithms and Applications", "Fall 2026", 3, "A/B", "Nagasri p"),
    ("FALL26_ASAC_CA_MCA_SEM3_B_E1CAB706", "Professional Skill Development", "Fall 2026", 3, "B", "Dharshinee Nagarajan"),
]


@router.post("/admin/catalog/import-mca")
def import_mca_catalog(admin: dict[str, Any] = Depends(require_role("admin"))) -> dict[str, Any]:
    """Idempotently import the MCA catalog transcribed from the admin-provided course list."""
    new_accounts: list[dict[str, str]] = []
    reused_faculty: set[str] = set()
    faculty_ids: dict[str, int] = {}
    subject_ids: dict[str, int] = {}
    subjects_created = 0
    subjects_updated = 0
    assignments_created = 0
    try:
        with engine.begin() as connection:
            course = connection.execute(text("SELECT id, name FROM courses WHERE UPPER(code) = 'MCA' ORDER BY id LIMIT 1 FOR UPDATE")).mappings().first()
            if course is None:
                course = connection.execute(text("""
                    INSERT INTO courses (name, code, description)
                    VALUES ('MCA', 'MCA', 'Master of Computer Applications')
                    RETURNING id, name
                """)).mappings().one()
            course_id = int(course["id"])

            for _, _, _, _, _, faculty_name in MCA_CATALOG_IMPORT:
                if faculty_name in faculty_ids:
                    continue
                existing = connection.execute(text("""
                    SELECT id FROM users
                    WHERE role = 'faculty' AND LOWER(full_name) = LOWER(:full_name)
                    ORDER BY id LIMIT 1
                """), {"full_name": faculty_name}).scalar_one_or_none()
                if existing is not None:
                    faculty_ids[faculty_name] = int(existing)
                    reused_faculty.add(faculty_name)
                    continue

                base_username = re.sub(r"[^a-z0-9]+", ".", faculty_name.casefold()).strip(".") or "faculty"
                username = base_username[:80]
                suffix = 1
                while connection.execute(text("SELECT 1 FROM users WHERE LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:email)"), {
                    "username": username,
                    "email": f"{username}@faculty.example.invalid",
                }).first() is not None:
                    tail = f".{suffix}"
                    username = f"{base_username[:80 - len(tail)]}{tail}"
                    suffix += 1
                email = f"{username}@faculty.example.invalid"
                initial_password = re.sub(r"[^A-Za-z0-9]", "", faculty_name) + "1234"
                row = connection.execute(text("""
                    INSERT INTO users (username, email, full_name, password_hash, role)
                    VALUES (:username, :email, :full_name, :password_hash, 'faculty')
                    RETURNING id
                """), {
                    "username": username,
                    "email": email,
                    "full_name": faculty_name,
                    "password_hash": password_hasher.hash(initial_password),
                }).mappings().one()
                faculty_ids[faculty_name] = int(row["id"])
                new_accounts.append({
                    "full_name": faculty_name,
                    "username": username,
                    "email": email,
                    "initial_password": initial_password,
                })

            for code, name, term, semester, section, faculty_name in MCA_CATALOG_IMPORT:
                subject = connection.execute(text("""
                    SELECT id FROM subjects WHERE UPPER(code) = UPPER(:code)
                    ORDER BY id LIMIT 1 FOR UPDATE
                """), {"code": code}).scalar_one_or_none()
                values = {
                    "course_id": course_id,
                    "code": code,
                    "name": name,
                    "semester": semester,
                    "term": term,
                    "instructor_name": faculty_name,
                    "section": section,
                }
                if subject is None:
                    subject_id = connection.execute(text("""
                        INSERT INTO subjects (course_id, code, name, semester, term, instructor_name, section)
                        VALUES (:course_id, :code, :name, :semester, :term, :instructor_name, :section)
                        RETURNING id
                    """), values).scalar_one()
                    subjects_created += 1
                else:
                    subject_id = connection.execute(text("""
                        UPDATE subjects
                        SET course_id = :course_id, name = :name, semester = :semester,
                            term = :term, instructor_name = :instructor_name, section = :section
                        WHERE id = :subject_id
                        RETURNING id
                    """), {**values, "subject_id": subject}).scalar_one()
                    subjects_updated += 1
                subject_ids[code] = int(subject_id)

                assignment_id = connection.execute(text("""
                    INSERT INTO faculty_subject_assignments (faculty_user_id, subject_id, assigned_by)
                    VALUES (:faculty_id, :subject_id, :admin_id)
                    ON CONFLICT (faculty_user_id, subject_id) DO NOTHING
                    RETURNING id
                """), {
                    "faculty_id": faculty_ids[faculty_name],
                    "subject_id": subject_id,
                    "admin_id": admin["id"],
                }).scalar_one_or_none()
                if assignment_id is not None:
                    assignments_created += 1
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="The MCA catalog import conflicted with existing account or catalog data; no changes were saved.") from error

    return {
        "course": {"id": course_id, "name": course["name"], "code": "MCA"},
        "subjects_total": len(MCA_CATALOG_IMPORT),
        "subjects_created": subjects_created,
        "subjects_updated": subjects_updated,
        "faculty_accounts_created": len(new_accounts),
        "faculty_accounts_reused": len(reused_faculty),
        "faculty_assignments_created": assignments_created,
        "existing_faculty": sorted(reused_faculty),
        "new_faculty_accounts": new_accounts,
        "email_note": "Generated addresses use the reserved .invalid domain and are placeholders; replace them with official emails before real use.",
        "password_note": "Initial passwords follow the requested name + 1234 pattern. They are demo-only and should be changed before real use.",
    }

@router.get("/catalog/specializations")
def get_specializations(
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, name FROM specializations ORDER BY name")
        ).mappings().all()
    return {"specializations": [dict(row) for row in rows]}

@router.get("/catalog/subjects")
def get_subjects(
    specialization_id: int | None = None,
    semester: int | None = None,
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT s.id, s.course_id, c.name AS course_name,
                       s.code, s.name, s.semester, s.term,
                       s.instructor_name, s.section, s.specialization_id,
                       p.name AS specialization_name
                FROM subjects AS s
                LEFT JOIN courses AS c ON c.id = s.course_id
                LEFT JOIN specializations AS p ON p.id = s.specialization_id
                WHERE (CAST(:specialization_id AS BIGINT) IS NULL OR s.specialization_id = :specialization_id)
                  AND (CAST(:semester AS INTEGER) IS NULL OR s.semester = :semester)
                ORDER BY s.term DESC NULLS LAST, p.name NULLS LAST, s.semester, s.name
            """),
            {"specialization_id": specialization_id, "semester": semester},
        ).mappings().all()
    return {"subjects": [dict(row) for row in rows]}

@router.post("/admin/specializations", status_code=201)
def create_specialization(
    specialization: SpecializationCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    name = specialization.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Specialization name must contain at least two characters.")
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text("INSERT INTO specializations (name) VALUES (:name) RETURNING id, name"),
                {"name": name},
            ).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That specialization already exists.") from error
    return dict(row)

@router.patch("/admin/specializations/{specialization_id}")
def update_specialization(
    specialization_id: int,
    specialization: SpecializationUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    name = specialization.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Specialization name must contain at least two characters.")
    try:
        with engine.begin() as connection:
            row = connection.execute(text("""
                UPDATE specializations SET name = :name
                WHERE id = :specialization_id RETURNING id, name
            """), {"name": name, "specialization_id": specialization_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That specialization name is already in use.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Specialization not found.")
    return dict(row)

@router.delete("/admin/specializations/{specialization_id}")
def delete_specialization(
    specialization_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        subject_count = connection.execute(text("""
            SELECT COUNT(*) FROM subjects WHERE specialization_id = :specialization_id
        """), {"specialization_id": specialization_id}).scalar_one()
        if subject_count:
            raise HTTPException(status_code=409, detail="Move or remove this specialization's subjects before deleting it.")
        deleted_id = connection.execute(text("""
            DELETE FROM specializations WHERE id = :specialization_id RETURNING id
        """), {"specialization_id": specialization_id}).scalar_one_or_none()
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Specialization not found.")
    return {"message": "Specialization removed."}

@router.post("/admin/subjects", status_code=201)
def create_subject(
    subject: SubjectCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    code = subject.code.strip().upper()
    name = subject.name.strip()
    if not code or len(name) < 2:
        raise HTTPException(status_code=422, detail="Enter a subject code and a name of at least two characters.")
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text("""
                    INSERT INTO subjects
                        (course_id, specialization_id, code, name, semester, term, instructor_name, section)
                    VALUES
                        (:course_id, :specialization_id, :code, :name, :semester, :term, :instructor_name, :section)
                    RETURNING id, course_id, specialization_id, code, name, semester, term, instructor_name, section
                """),
                {
                    "course_id": subject.course_id,
                    "specialization_id": subject.specialization_id,
                    "code": code,
                    "name": name,
                    "semester": subject.semester,
                    "term": subject.term.strip() if subject.term else None,
                    "instructor_name": subject.instructor_name.strip() if subject.instructor_name else None,
                    "section": subject.section.strip() if subject.section else None,
                },
            ).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="This subject code or name is already listed for that specialization and semester.") from error
    return dict(row)

@router.patch("/admin/subjects/{subject_id}")
def update_subject(
    subject_id: int,
    changes: SubjectUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Enter at least one subject field to update.")
    values = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
    fields = ", ".join(f"{key} = :{key}" for key in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE subjects SET {fields}
                WHERE id = :subject_id
                RETURNING id, course_id, specialization_id, code, name, semester, term, instructor_name, section
            """), {**values, "subject_id": subject_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="A subject with these details already exists, or the specialization is invalid.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    return dict(row)

@router.delete("/admin/subjects/{subject_id}")
def delete_subject(
    subject_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        deleted_id = connection.execute(text("""
            DELETE FROM subjects WHERE id = :subject_id RETURNING id
        """), {"subject_id": subject_id}).scalar_one_or_none()
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    return {"message": "Subject removed."}

@router.get("/admin/dashboard/summary")
def admin_dashboard_summary(
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, int]:
    with engine.connect() as connection:
        counts = connection.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE role = 'student') AS students,
                (SELECT COUNT(*) FROM users WHERE role = 'faculty') AS faculty,
                (SELECT COUNT(*) FROM courses) AS courses,
                (SELECT COUNT(*) FROM subjects) AS subjects,
                (SELECT COUNT(*) FROM departments) AS departments
        """)).mappings().one()
    return {key: int(value) for key, value in counts.items()}

@router.get("/admin/departments")
def list_departments(
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    where = ""
    if search and search.strip():
        where = " WHERE name ILIKE :search OR code ILIKE :search"
        params["search"] = f"%{search.strip()}%"
    with engine.connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM departments{where}"), params).scalar_one()
        rows = connection.execute(text(f"""
            SELECT d.id, d.name, d.code, d.created_at, d.updated_at,
                   COUNT(c.id)::INTEGER AS course_count
            FROM departments d LEFT JOIN courses c ON c.department_id = d.id
            {where}
            GROUP BY d.id ORDER BY d.name LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"departments": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@router.post("/admin/departments", status_code=201)
def create_department(
    item: DepartmentCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            row = connection.execute(text("""
                INSERT INTO departments (name, code) VALUES (:name, :code)
                RETURNING id, name, code, created_at, updated_at
            """), {"name": item.name.strip(), "code": item.code.strip().upper()}).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="A department with that name or code already exists.") from error
    return dict(row)

@router.patch("/admin/departments/{department_id}")
def update_department(
    department_id: int,
    changes: DepartmentUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Enter at least one field to update.")
    values = {key: (value.strip().upper() if key == "code" and value else value.strip() if value else value) for key, value in values.items()}
    assignments = ", ".join(f"{key} = :{key}" for key in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE departments SET {assignments}, updated_at = NOW()
                WHERE id = :department_id
                RETURNING id, name, code, created_at, updated_at
            """), {**values, "department_id": department_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="A department with that name or code already exists.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Department not found.")
    return dict(row)

@router.delete("/admin/departments/{department_id}")
def delete_department(
    department_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        result = connection.execute(text("DELETE FROM departments WHERE id = :id RETURNING id"), {"id": department_id}).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Department not found.")
    return {"message": "Department removed. Its courses are now unassigned."}

@router.get("/admin/courses")
def list_courses(
    search: str | None = None,
    department_id: int | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    clauses, params = [], {"limit": limit, "offset": offset}
    if search and search.strip():
        clauses.append("(c.name ILIKE :search OR c.code ILIKE :search)")
        params["search"] = f"%{search.strip()}%"
    if department_id is not None:
        clauses.append("c.department_id = :department_id")
        params["department_id"] = department_id
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with engine.connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM courses c{where}"), params).scalar_one()
        rows = connection.execute(text(f"""
            SELECT c.id, c.name, c.code, c.description, c.is_active,
                   c.department_id, d.name AS department_name, c.created_at, c.updated_at,
                   COUNT(s.id)::INTEGER AS subject_count
            FROM courses c LEFT JOIN departments d ON d.id = c.department_id
            LEFT JOIN subjects s ON s.course_id = c.id
            {where}
            GROUP BY c.id, d.name ORDER BY c.name LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"courses": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@router.post("/admin/courses", status_code=201)
def create_course(
    item: CourseCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    try:
        with engine.begin() as connection:
            row = connection.execute(text("""
                INSERT INTO courses (name, code, department_id, description, is_active)
                VALUES (:name, :code, :department_id, :description, :is_active)
                RETURNING id, name, code, department_id, description, is_active, created_at, updated_at
            """), {
                "name": item.name.strip(), "code": item.code.strip().upper(),
                "department_id": item.department_id,
                "description": item.description.strip() if item.description else None,
                "is_active": item.is_active,
            }).mappings().one()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That course code or department and course name already exists, or the department is invalid.") from error
    return dict(row)

@router.patch("/admin/courses/{course_id}")
def update_course(
    course_id: int,
    changes: CourseUpdate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Enter at least one field to update.")
    values = {key: (value.strip().upper() if key == "code" and value else value.strip() if isinstance(value, str) else value) for key, value in values.items()}
    assignments = ", ".join(f"{key} = :{key}" for key in values)
    try:
        with engine.begin() as connection:
            row = connection.execute(text(f"""
                UPDATE courses SET {assignments}, updated_at = NOW()
                WHERE id = :course_id
                RETURNING id, name, code, department_id, description, is_active, created_at, updated_at
            """), {**values, "course_id": course_id}).mappings().one_or_none()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="The course details conflict with an existing course, or the department is invalid.") from error
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    return dict(row)

@router.delete("/admin/courses/{course_id}")
def delete_course(
    course_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        result = connection.execute(text("DELETE FROM courses WHERE id = :id RETURNING id"), {"id": course_id}).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    return {"message": "Course and its linked subjects and faculty assignments were removed."}

@router.get("/admin/subjects")
def list_subjects_admin(
    search: str | None = None,
    course_id: int | None = None,
    specialization_id: int | None = None,
    semester: int | None = None,
    limit: int = 25,
    offset: int = 0,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    clauses, params = [], {"limit": limit, "offset": offset}
    if search and search.strip():
        clauses.append("(s.name ILIKE :search OR s.code ILIKE :search)")
        params["search"] = f"%{search.strip()}%"
    if course_id is not None:
        clauses.append("s.course_id = :course_id")
        params["course_id"] = course_id
    if specialization_id is not None:
        clauses.append("s.specialization_id = :specialization_id")
        params["specialization_id"] = specialization_id
    if semester is not None:
        clauses.append("s.semester = :semester")
        params["semester"] = semester
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with engine.connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM subjects s{where}"), params).scalar_one()
        rows = connection.execute(text(f"""
            SELECT s.id, s.course_id, c.name AS course_name, s.specialization_id,
                   p.name AS specialization_name, s.code, s.name, s.semester,
                   s.term, s.section, s.instructor_name, s.created_at,
                   COALESCE(array_agg(DISTINCT jsonb_build_object(
                       'id', u.id, 'username', u.username, 'full_name', u.full_name
                   )) FILTER (WHERE u.id IS NOT NULL), ARRAY[]::JSONB[]) AS faculty
            FROM subjects s
            LEFT JOIN courses c ON c.id = s.course_id
            LEFT JOIN specializations p ON p.id = s.specialization_id
            LEFT JOIN faculty_subject_assignments a ON a.subject_id = s.id
            LEFT JOIN users u ON u.id = a.faculty_user_id
            {where}
            GROUP BY s.id, c.name, p.name
            ORDER BY s.semester, s.name LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return {"subjects": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@router.get("/admin/options")
def admin_select_options(
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    with engine.connect() as connection:
        faculty = connection.execute(text("SELECT id, full_name, username FROM users WHERE role = 'faculty' ORDER BY full_name, username")).mappings().all()
        students = connection.execute(text("SELECT id, full_name, username FROM users WHERE role = 'student' ORDER BY full_name, username")).mappings().all()
        departments = connection.execute(text("SELECT id, name, code FROM departments ORDER BY name")).mappings().all()
        courses = connection.execute(text("SELECT id, name, code FROM courses WHERE is_active ORDER BY name")).mappings().all()
        specializations = connection.execute(text("SELECT id, name FROM specializations ORDER BY name")).mappings().all()
        subjects = connection.execute(text("SELECT id, name, code, semester, term, section, course_id, specialization_id FROM subjects ORDER BY semester, name")).mappings().all()
        terms_sections = connection.execute(text("""
            SELECT DISTINCT term, section FROM subjects
            WHERE term IS NOT NULL OR section IS NOT NULL
            ORDER BY term NULLS LAST, section NULLS LAST
        """)).mappings().all()
    return {
        "faculty": [dict(row) for row in faculty],
        "students": [dict(row) for row in students],
        "departments": [dict(row) for row in departments],
        "courses": [dict(row) for row in courses],
        "specializations": [dict(row) for row in specializations],
        "subjects": [dict(row) for row in subjects],
        "term_sections": [dict(row) for row in terms_sections],
        "semesters": [1, 2, 3, 4, 5, 6],
    }

@router.delete("/admin/bulk/{entity}")
def bulk_delete_admin_records(
    entity: Literal["faculty", "students", "subjects", "courses", "departments"],
    selection: BulkIds,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    ids = list(dict.fromkeys(selection.ids))
    if len(ids) != len(selection.ids):
        raise HTTPException(status_code=422, detail="Remove duplicate IDs from the selection.")
    delete_sql = {
        "faculty": "DELETE FROM users WHERE role = 'faculty' AND id IN :ids RETURNING id",
        "students": "DELETE FROM users WHERE role = 'student' AND id IN :ids RETURNING id",
        "subjects": "DELETE FROM subjects WHERE id IN :ids RETURNING id",
        "courses": "DELETE FROM courses WHERE id IN :ids RETURNING id",
        "departments": "DELETE FROM departments WHERE id IN :ids RETURNING id",
    }[entity]
    try:
        with engine.begin() as connection:
            deleted = connection.execute(text(delete_sql).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).scalars().all()
    except IntegrityError as error:
        detail = "Some selected student records have attendance history and cannot be removed." if entity == "students" else "Some selected records are linked to data that prevents deletion."
        raise HTTPException(status_code=409, detail=detail) from error
    return {"deleted_count": len(deleted), "requested_count": len(ids)}
