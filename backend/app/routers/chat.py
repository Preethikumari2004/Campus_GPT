from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..database import engine
from ..security import get_current_user
from ..schemas import ChatRequest
from ..services.live_answers import answer_campus_calendar_question, answer_catalog_faculty_question, answer_faculty_directory_question, answer_faculty_subject_question, answer_student_subject_question, answer_subject_catalog_question
from ..services.llm import ask_model
from ..services.rag import retrieve
from typing import Any
import json, re
from sqlalchemy import text

router = APIRouter()


@router.post("/chat")
def chat(
    request: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["role"] == "student" and request.conversation_id is not None:
        with engine.connect() as connection:
            owned = connection.execute(text("""
                SELECT 1 FROM student_chat_conversations
                WHERE id = :conversation_id AND student_user_id = :student_id
            """), {"conversation_id": request.conversation_id, "student_id": current_user["id"]}).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    asks_for_private_faculty_assignment = current_user.get("role") != "admin" and bool(
        re.search(
            r"\bwho\s+(?:teaches?|is\s+(?:the\s+)?(?:faculty|teacher|instructor))\b|"
            r"\b(?:faculty|teacher|instructor)\s+(?:for|of)\b",
            request.question,
            re.IGNORECASE,
        )
    )
    if asks_for_private_faculty_assignment:
        live_answer = "Faculty assignment details are available to administrators. Please ask your admin."
    else:
        live_answer = answer_student_subject_question(request.question, current_user)
        if live_answer is None:
            live_answer = answer_faculty_subject_question(request.question, current_user)
    # Admin-managed live records (catalog, faculty directory, calendar) are
    # private to admins. Faculty and students can still use college-wide
    # documents through the normal role-scoped RAG path below.
    if live_answer is None and current_user["role"] == "admin":
        live_answer = answer_catalog_faculty_question(request.question)
        if live_answer is None:
            live_answer = answer_subject_catalog_question(request.question)
        if live_answer is None:
            live_answer = answer_faculty_directory_question(request.question)
        if live_answer is None:
            live_answer = answer_campus_calendar_question(request.question)

    if live_answer is not None:
        answer = live_answer
        cited_sources: list[dict[str, Any]] = []
    else:
        sources = retrieve(request.question, current_user, history=request.history)
        if not sources:
            answer = ask_model(request.question, sources, request.history)
            cited_sources = []
        else:
            answer = ask_model(request.question, sources, request.history)
            cited_sources = [
                {"id": index, "filename": item["source"], "excerpt": item["text"]}
                for index, item in enumerate(sources, start=1)
            ]

    if isinstance(answer, dict):
        answer = next(
            (answer[key] for key in ("answer", "text", "content", "message", "detail") if isinstance(answer.get(key), str)),
            json.dumps(answer, ensure_ascii=False),
        )
    elif not isinstance(answer, str):
        answer = str(answer)
    answer = re.sub(r"\s*\[object Object\]\s*", " ", answer).strip()

    conversation_id = None
    if current_user["role"] == "student":
        with engine.begin() as connection:
            if request.conversation_id is None:
                conversation_id = connection.execute(text("""
                    INSERT INTO student_chat_conversations (student_user_id, title)
                    VALUES (:student_id, :title)
                    RETURNING id
                """), {
                    "student_id": current_user["id"],
                    "title": request.question.strip()[:120],
                }).scalar_one()
            else:
                conversation_id = request.conversation_id
            connection.execute(text("""
                INSERT INTO student_chat_turns (conversation_id, question, answer, sources)
                VALUES (:conversation_id, :question, :answer, CAST(:sources AS JSONB))
            """), {
                "conversation_id": conversation_id,
                "question": request.question.strip(),
                "answer": answer,
                "sources": json.dumps(cited_sources, ensure_ascii=False),
            })
            connection.execute(text("""
                UPDATE student_chat_conversations
                SET updated_at = NOW()
                WHERE id = :conversation_id AND student_user_id = :student_id
            """), {"conversation_id": conversation_id, "student_id": current_user["id"]})

    return {"answer": answer, "sources": cited_sources, "conversation_id": conversation_id}
