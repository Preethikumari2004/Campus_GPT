from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..database import engine
from ..security import get_current_user, require_role
from ..schemas import DocumentRequest
from ..config import KNOWLEDGE_DIR, MAX_KNOWLEDGE_FILE_BYTES, SUPPORTED_KNOWLEDGE_SUFFIXES
from ..services.document_text import accessible_document_rows, extract_document_text, invalidate_vector_index
from typing import Any, Literal
from pathlib import Path
from sqlalchemy import text

router = APIRouter()


@router.get("/documents")
def list_documents(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    rows = accessible_document_rows(current_user)
    # College document contents feed answers for faculty and students, but the
    # filenames and upload records are visible only in the admin document area.
    if current_user["role"] != "admin":
        rows = [row for row in rows if row["scope"] != "campus"]
    for row in rows:
        row["can_delete"] = (
            current_user["role"] == "admin"
            or (
                row["uploaded_by"] == current_user["id"]
                and row["scope"] in {"course", "private", "submission"}
            )
        )
    return {"documents": rows}

@router.post("/documents/upload", status_code=201)
async def upload_knowledge_document(
    request: Request,
    filename: str = Query(min_length=1, max_length=200),
    document_type: Literal["campus", "course", "personal", "submission"] = "personal",
    subject_id: int | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    safe_name = Path(filename.replace("\\", "/")).name
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in SUPPORTED_KNOWLEDGE_SUFFIXES:
        raise HTTPException(status_code=415, detail="Choose a PDF, Word (.docx), text (.txt), or Markdown (.md) file.")

    file_bytes = await request.body()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="The selected file is empty.")
    if len(file_bytes) > MAX_KNOWLEDGE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Files must be 10 MB or smaller.")

    try:
        extracted_text = extract_document_text(safe_name, file_bytes)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail="This file could not be read. Check that it is a valid, unlocked PDF or DOCX.") from error
    if not extracted_text.strip():
        detail = "No selectable text was found in this PDF. Scanned PDFs need OCR before CampusAI can read them." if suffix == ".pdf" else "No readable text was found in this document."
        raise HTTPException(status_code=422, detail=detail)

    scope: str
    if current_user["role"] == "admin":
        if document_type != "campus" or subject_id is not None:
            raise HTTPException(status_code=403, detail="Admins can upload college reference documents for CampusGPT.")
        scope = "campus"
    elif current_user["role"] == "faculty":
        if document_type != "course" or subject_id is None:
            raise HTTPException(status_code=422, detail="Choose one of your assigned subjects for this faculty resource.")
        with engine.connect() as connection:
            assigned = connection.execute(text("""
                SELECT 1 FROM faculty_subject_assignments
                WHERE faculty_user_id = :faculty_id AND subject_id = :subject_id
            """), {"faculty_id": current_user["id"], "subject_id": subject_id}).scalar_one_or_none()
        if not assigned:
            raise HTTPException(status_code=403, detail="You can upload course resources only for subjects assigned to you.")
        scope = "course"
    else:
        if document_type == "personal":
            if subject_id is not None:
                raise HTTPException(status_code=422, detail="Personal notes do not need a subject selection.")
            scope = "private"
        elif document_type == "submission":
            if subject_id is None:
                raise HTTPException(status_code=422, detail="Choose the subject for this assignment submission.")
            with engine.connect() as connection:
                enrolled = connection.execute(text("""
                    SELECT 1 FROM student_subject_enrollments
                    WHERE student_user_id = :student_id AND subject_id = :subject_id
                """), {"student_id": current_user["id"], "subject_id": subject_id}).scalar_one_or_none()
                has_faculty = connection.execute(text("""
                    SELECT 1 FROM faculty_subject_assignments WHERE subject_id = :subject_id
                """), {"subject_id": subject_id}).scalar_one_or_none()
            if not enrolled:
                raise HTTPException(status_code=403, detail="You are not enrolled in that subject.")
            if not has_faculty:
                raise HTTPException(status_code=409, detail="That subject has no assigned faculty to receive the submission.")
            scope = "submission"
        else:
            raise HTTPException(status_code=403, detail="Students can upload private notes or assignment submissions.")

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    destination = KNOWLEDGE_DIR / safe_name
    if destination.exists():
        raise HTTPException(status_code=409, detail="A document with this filename already exists. Rename the file and try again.")
    destination.write_bytes(file_bytes)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO knowledge_documents (filename, scope, subject_id, uploaded_by)
                VALUES (:filename, :scope, :subject_id, :uploaded_by)
            """), {
                "filename": safe_name,
                "scope": scope,
                "subject_id": subject_id if scope in {"course", "submission"} else None,
                "uploaded_by": current_user["id"],
            })
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Could not save document access details. Try again with a different filename.") from error
    invalidate_vector_index()
    return {"message": "Document uploaded with the correct access permissions.", "filename": safe_name, "scope": scope}

@router.delete("/documents/{filename}")
def delete_knowledge_document(
    filename: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    safe_name = Path(filename.replace("\\", "/")).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in SUPPORTED_KNOWLEDGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Invalid knowledge document name.")
    with engine.connect() as connection:
        document = connection.execute(text("""
            SELECT id, scope, uploaded_by FROM knowledge_documents WHERE filename = :filename
        """), {"filename": safe_name}).mappings().one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    can_delete = current_user["role"] == "admin" or (
        document["uploaded_by"] == current_user["id"]
        and document["scope"] in {"course", "private", "submission"}
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="You can remove only your own uploaded document.")
    destination = KNOWLEDGE_DIR / safe_name
    if destination.is_file():
        destination.unlink()
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM knowledge_documents WHERE id = :id"), {"id": document["id"]})
    invalidate_vector_index()
    return {"message": "Knowledge document removed.", "filename": safe_name}

@router.post("/documents")
def add_document(
    document: DocumentRequest,
    admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    safe_name = Path(document.filename).name
    if Path(safe_name).suffix.lower() not in {".txt", ".md"}:
        raise HTTPException(status_code=415, detail="For this MVP, upload plain text or Markdown (.txt, .md).")
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    destination = KNOWLEDGE_DIR / safe_name
    if destination.exists():
        raise HTTPException(status_code=409, detail="A document with this filename already exists.")
    destination.write_text(document.content, encoding="utf-8")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO knowledge_documents (filename, scope, subject_id, uploaded_by)
                VALUES (:filename, 'campus', NULL, :uploaded_by)
            """), {"filename": safe_name, "uploaded_by": admin["id"]})
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Could not save document access details.") from error
    invalidate_vector_index()
    return {"message": "Document added to the knowledge base.", "filename": safe_name}
