from __future__ import annotations
from fastapi import APIRouter, HTTPException
from ..database import engine
from ..services.llm import campusgpt_local_only
import os
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from error

    return {
        "status": "ok",
        "service": "MCA CampusAI API",
        "database": "connected",
        "campusgpt_mode": (
            "keyword_rag_with_groq" if os.getenv("GROQ_API_KEY") and not campusgpt_local_only()
            else "keyword_rag_local"
        ),
    }
