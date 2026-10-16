from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import ensure_demo_accounts, init_db
from app.routers import admin_assignments, admin_catalog, admin_users, attendance, auth, chat, class_assignments, documents, events, faculty, health, profile, student

init_db()
ensure_demo_accounts()

app = FastAPI(title="MCA CampusAI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Welcome to MCA CampusAI!", "docs": "/docs"}


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin_users.router)
app.include_router(admin_catalog.router)
app.include_router(admin_assignments.router)
app.include_router(events.router)
app.include_router(faculty.router)
app.include_router(student.router)
app.include_router(class_assignments.router)
app.include_router(attendance.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(health.router)
