from __future__ import annotations
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    conversation_id: int | None = Field(default=None, gt=0)

class DocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1_000_000)

class StudentSubjectEnrollmentCreate(BaseModel):
    student_id: int
    subject_ids: list[int] = Field(min_length=1, max_length=100)

class AccountCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "faculty", "admin"]

class FacultyCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)

class FacultyUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=120)

class FacultyProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    current_password: str | None = Field(default=None, min_length=8, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AttendanceEntry(BaseModel):
    student_id: int
    status: Literal["present", "absent"]

class AttendanceCreate(BaseModel):
    subject_id: int | None = None
    course_name: str | None = Field(default=None, min_length=2, max_length=160)
    session_date: date
    records: list[AttendanceEntry] = Field(min_length=1, max_length=500)

class ClassAssignmentCreate(BaseModel):
    subject_id: int
    title: str = Field(min_length=3, max_length=180)
    instructions: str = Field(min_length=5, max_length=10000)
    due_at: datetime

class ClassAssignmentSubmissionCreate(BaseModel):
    response_text: str = Field(default="", max_length=20000)

class ClassAssignmentReview(BaseModel):
    score: float | None = Field(default=None, ge=0, le=100)
    feedback: str | None = Field(default=None, max_length=4000)

class SpecializationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)

class SpecializationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)

class CampusEventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    event_type: Literal['academic', 'exam', 'campus', 'deadline']
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)

class SubjectCreate(BaseModel):
    course_id: int
    specialization_id: int | None = None
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    semester: int = Field(ge=1, le=6)
    term: str | None = Field(default=None, max_length=40)
    instructor_name: str | None = Field(default=None, max_length=120)
    section: str | None = Field(default=None, max_length=40)

class SubjectUpdate(BaseModel):
    course_id: int | None = None
    specialization_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    semester: int | None = Field(default=None, ge=1, le=6)
    term: str | None = Field(default=None, max_length=40)
    instructor_name: str | None = Field(default=None, max_length=120)
    section: str | None = Field(default=None, max_length=40)

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=40)

class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=40)

class CourseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=80)
    department_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code: str | None = Field(default=None, min_length=2, max_length=80)
    department_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

class StudentCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)

class StudentUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=120)

class AssignmentCreate(BaseModel):
    faculty_id: int
    subject_id: int

class AssignmentUpdate(BaseModel):
    faculty_id: int | None = None
    subject_id: int | None = None

class BulkAssignmentCreate(BaseModel):
    assignments: list[AssignmentCreate] = Field(min_length=1, max_length=500)

class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
