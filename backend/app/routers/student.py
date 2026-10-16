from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import require_role
from typing import Any
from sqlalchemy import text

router = APIRouter()


@router.get("/student/subjects")
def list_student_subjects(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.id, s.course_id, c.name AS course_name,
                   s.name, s.code, s.semester, s.term, s.section,
                   s.specialization_id, p.name AS specialization_name,
                   COALESCE(
                       STRING_AGG(DISTINCT f.full_name, ', ' ORDER BY f.full_name),
                       s.instructor_name
                   ) AS instructor_name
            FROM student_subject_enrollments e
            JOIN subjects s ON s.id = e.subject_id
            LEFT JOIN courses c ON c.id = s.course_id
            LEFT JOIN specializations p ON p.id = s.specialization_id
            LEFT JOIN faculty_subject_assignments a ON a.subject_id = s.id
            LEFT JOIN users f ON f.id = a.faculty_user_id AND f.role = 'faculty'
            WHERE e.student_user_id = :student_id
            GROUP BY s.id, c.name, p.name
            ORDER BY s.semester, s.name
        """), {"student_id": student["id"]}).mappings().all()
    return {"subjects": [dict(row) for row in rows]}

@router.get("/student/chat-history")
def list_student_chat_history(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(t.id)::INTEGER AS message_count
            FROM student_chat_conversations c
            LEFT JOIN student_chat_turns t ON t.conversation_id = c.id
            WHERE c.student_user_id = :student_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
        """), {"student_id": student["id"]}).mappings().all()
    return {"conversations": [dict(row) for row in rows]}

@router.get("/student/chat-history/{conversation_id}")
def read_student_chat_history(
    conversation_id: int,
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, Any]:
    with engine.connect() as connection:
        conversation = connection.execute(text("""
            SELECT id, title, created_at, updated_at
            FROM student_chat_conversations
            WHERE id = :conversation_id AND student_user_id = :student_id
        """), {"conversation_id": conversation_id, "student_id": student["id"]}).mappings().one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        turns = connection.execute(text("""
            SELECT id, question, answer, sources, created_at
            FROM student_chat_turns
            WHERE conversation_id = :conversation_id
            ORDER BY created_at, id
        """), {"conversation_id": conversation_id}).mappings().all()
    return {"conversation": dict(conversation), "turns": [dict(turn) for turn in turns]}

@router.delete("/student/chat-history/{conversation_id}")
def delete_student_chat_history_item(
    conversation_id: int,
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, str]:
    with engine.begin() as connection:
        deleted = connection.execute(text("""
            DELETE FROM student_chat_conversations
            WHERE id = :conversation_id AND student_user_id = :student_id
            RETURNING id
        """), {"conversation_id": conversation_id, "student_id": student["id"]}).scalar_one_or_none()
    if deleted is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"message": "Conversation deleted."}

@router.delete("/student/chat-history")
def clear_student_chat_history(
    student: dict[str, Any] = Depends(require_role("student")),
) -> dict[str, int]:
    with engine.begin() as connection:
        deleted_ids = connection.execute(text("""
            DELETE FROM student_chat_conversations
            WHERE student_user_id = :student_id
            RETURNING id
        """), {"student_id": student["id"]}).scalars().all()
    return {"deleted_count": len(deleted_ids)}
