from __future__ import annotations
import logging, os, re
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from the project .env file")

# Preserve the original PostgreSQL driver fallback.
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is missing from the project .env file")

JWT_ALGORITHM = "HS256"
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge_base"
ASSIGNMENT_SUBMISSION_DIR = PROJECT_ROOT / "data" / "assignment_submissions"
MAX_ASSIGNMENT_ATTACHMENT_BYTES = 10 * 1024 * 1024
ASSIGNMENT_ATTACHMENT_SUFFIXES = {
    ".pdf", ".docx", ".txt", ".md", ".py", ".java", ".js", ".jsx",
    ".html", ".css", ".zip", ".png", ".jpg", ".jpeg",
}
VECTOR_INDEX = KNOWLEDGE_DIR / ".vector_index.json"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SUPPORTED_KNOWLEDGE_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}
MAX_KNOWLEDGE_FILE_BYTES = 10 * 1024 * 1024
logger = logging.getLogger("campusgpt")
