from __future__ import annotations
from ..database import engine
from typing import Any
import re
from sqlalchemy import text
from datetime import timedelta, timezone

def answer_catalog_faculty_question(question: str) -> str | None:
    """Answer exact subject/faculty lookups from the structured MCA catalog."""
    if not re.search(r"\b(who|faculty|instructor|teacher|teach|teaches|teaching)\b", question, re.IGNORECASE):
        return None

    normalize = lambda value: re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    normalized_question = normalize(question)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.name, s.instructor_name,
                   string_agg(DISTINCT u.full_name, ', ' ORDER BY u.full_name) AS assigned_faculty
            FROM subjects s
            LEFT JOIN faculty_subject_assignments a ON a.subject_id = s.id
            LEFT JOIN users u ON u.id = a.faculty_user_id
            GROUP BY s.id, s.name, s.instructor_name
            ORDER BY s.name
        """)).mappings().all()

    matches = [row for row in rows if normalize(row["name"]) and normalize(row["name"]) in normalized_question]
    if not matches:
        return None

    subject_names = {row["name"] for row in matches}
    if len(subject_names) != 1:
        return None
    subject_name = next(iter(subject_names))
    faculty_names = sorted({
        name.strip()
        for row in matches
        for name in (row["assigned_faculty"] or row["instructor_name"] or "").split(",")
        if name.strip()
    })
    if not faculty_names:
        return f"I couldn’t find a faculty member listed for {subject_name} in the subject catalog."
    return f"{', '.join(faculty_names)} teaches {subject_name}."

def answer_faculty_directory_question(question: str) -> str | None:
    """Answer campus-wide faculty directory questions without exposing account details."""
    asks_for_faculty = re.search(r"\b(faculty|teachers?|instructors?)\b", question, re.IGNORECASE)
    asks_for_list = re.search(
        r"\b(who|which|list|show|names?|teach|teaches|teaching|faculty)\b",
        question,
        re.IGNORECASE,
    )
    if not asks_for_faculty or not asks_for_list:
        return None

    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT u.full_name,
                   string_agg(DISTINCT s.name, ', ' ORDER BY s.name) AS subjects
            FROM users u
            LEFT JOIN faculty_subject_assignments a ON a.faculty_user_id = u.id
            LEFT JOIN subjects s ON s.id = a.subject_id
            WHERE u.role = 'faculty'
            GROUP BY u.id, u.full_name
            ORDER BY u.full_name
            LIMIT 30
        """)).mappings().all()

    normalized_question = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    name_matches = [
        row for row in rows
        if re.sub(r"[^a-z0-9]+", " ", row["full_name"].lower()).strip() in normalized_question
    ]
    if name_matches:
        results = name_matches
    elif re.search(r"\b(list|show|who are|which)\b", question, re.IGNORECASE):
        results = rows
    else:
        return None

    if not results:
        return "There are no faculty accounts in the system yet."
    entries = [
        f"{row['full_name']}" + (f" — teaches {row['subjects']}" if row.get("subjects") else " — no subjects assigned yet")
        for row in results
    ]
    return "Faculty in the MCA system: " + "; ".join(entries) + "."

def answer_student_subject_question(question: str, current_user: dict[str, Any]) -> str | None:
    """Answer a student's personal subject-list question from their enrollments."""
    asks_about_subjects = re.search(r"\b(subjects?|courses?)\b", question, re.IGNORECASE)
    asks_about_self = re.search(
        r"\b(my|me|i|enrolled|taking|this semester|current semester)\b",
        question,
        re.IGNORECASE,
    )
    if current_user.get("role") != "student" or not asks_about_subjects or not asks_about_self:
        return None

    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.name, s.code, s.semester, s.term
            FROM student_subject_enrollments e
            JOIN subjects s ON s.id = e.subject_id
            WHERE e.student_user_id = :student_id
            ORDER BY s.semester, s.name
        """), {"student_id": current_user["id"]}).mappings().all()

    if not rows:
        return "No subjects are currently linked to your student account. Please ask your admin to check your enrollment."

    subject_details = []
    for row in rows:
        details = [f"Semester {row['semester']}"]
        if row.get("term"):
            details.append(str(row["term"]))
        if row.get("code"):
            details.append(str(row["code"]))
        subject_details.append(f"{row['name']} ({', '.join(details)})")
    return "The subjects currently linked to your account are: " + "; ".join(subject_details) + "."

def answer_faculty_subject_question(question: str, current_user: dict[str, Any]) -> str | None:
    """Answer a faculty member's own assigned-subject question from the catalog."""
    asks_about_my_classes = re.search(
        r"\b(my|mine|assigned|teaching|teach)\b", question, re.IGNORECASE
    ) and re.search(r"\b(subjects?|courses?|classes?)\b", question, re.IGNORECASE)
    if current_user.get("role") != "faculty" or not asks_about_my_classes:
        return None

    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT s.name, s.code, s.semester, s.term, s.section
            FROM faculty_subject_assignments a
            JOIN subjects s ON s.id = a.subject_id
            WHERE a.faculty_user_id = :faculty_id
            ORDER BY s.semester, s.name
        """), {"faculty_id": current_user["id"]}).mappings().all()

    if not rows:
        return "No subjects are currently assigned to your faculty account. Please ask your admin to check your assignments."

    details = []
    for row in rows:
        labels = [f"Semester {row['semester']}"]
        if row.get("term"):
            labels.append(str(row["term"]))
        if row.get("section"):
            labels.append(f"Section {row['section']}")
        details.append(f"{row['name']} ({', '.join(labels)})")
    return "Your assigned subjects are: " + "; ".join(details) + "."

def answer_subject_catalog_question(question: str) -> str | None:
    """Answer campus-wide questions about the current subject catalog."""
    asks_for_catalog = re.search(
        r"\b(subjects?|courses?|catalog|curriculum|specialization)\b", question, re.IGNORECASE
    ) and re.search(
        r"\b(what|which|list|available|offered|offer|new|added|catalog|semester|sem|specialization|code)\b",
        question,
        re.IGNORECASE,
    )
    if not asks_for_catalog:
        return None

    semester_match = re.search(r"\b(?:semester|sem)\s*[-:]?\s*([1-6])\b", question, re.IGNORECASE)
    params: dict[str, Any] = {}
    filters: list[str] = []
    if semester_match:
        filters.append("s.semester = :semester")
        params["semester"] = int(semester_match.group(1))
    asks_for_recent_additions = bool(re.search(r"\b(new|newly|recent|added|latest)\b", question, re.IGNORECASE))
    if asks_for_recent_additions:
        filters.append("s.created_at >= NOW() - INTERVAL '30 days'")
    where_clause = "WHERE " + " AND ".join(filters) if filters else ""
    ordering = "s.created_at DESC, s.semester, s.name" if asks_for_recent_additions else "s.semester, s.name"

    with engine.connect() as connection:
        rows = connection.execute(text(f"""
            SELECT s.name, s.code, s.semester, s.term, s.section,
                   string_agg(DISTINCT u.full_name, ', ' ORDER BY u.full_name) AS assigned_faculty,
                   s.instructor_name
            FROM subjects s
            LEFT JOIN faculty_subject_assignments a ON a.subject_id = s.id
            LEFT JOIN users u ON u.id = a.faculty_user_id AND u.role = 'faculty'
            {where_clause}
            GROUP BY s.id, s.name, s.code, s.semester, s.term, s.section, s.instructor_name
            ORDER BY {ordering}
            LIMIT 30
        """), params).mappings().all()

    if not rows:
        if asks_for_recent_additions:
            return "No new subjects have been added to the catalog in the last 30 days."
        if semester_match:
            return f"I couldn’t find any subjects listed for Semester {semester_match.group(1)} yet."
        return "I couldn’t find any subjects in the current catalog yet."

    entries = []
    for row in rows:
        details = [f"Semester {row['semester']}"]
        if row.get("term"):
            details.append(str(row["term"]))
        if row.get("code"):
            details.append(f"Code {row['code']}")
        faculty = row.get("assigned_faculty") or row.get("instructor_name")
        if faculty:
            details.append(f"Faculty: {faculty}")
        entries.append(f"{row['name']} ({', '.join(details)})")

    heading = f"Semester {semester_match.group(1)} subjects" if semester_match else "Subjects in the current MCA catalog"
    return heading + ": " + "; ".join(entries) + "."

def answer_campus_calendar_question(question: str) -> str | None:
    """Answer campus event, exam-date, and calendar questions from current admin data."""
    asks_about_calendar = re.search(
        r"\b(calendar|events?|exam|deadline|upcoming|schedule|date|latest updates?|recent updates?)\b",
        question,
        re.IGNORECASE,
    )
    if not asks_about_calendar:
        return None

    asks_about_past = re.search(r"\b(past|previous|last|happened|held)\b", question, re.IGNORECASE)
    time_filter = "start_at < NOW()" if asks_about_past else "start_at >= NOW()"
    type_filter = ""
    if re.search(r"\bexams?\b", question, re.IGNORECASE):
        type_filter = "AND event_type = 'exam'"
    elif re.search(r"\bdeadlines?\b", question, re.IGNORECASE):
        type_filter = "AND event_type = 'deadline'"

    with engine.connect() as connection:
        rows = connection.execute(text(f"""
            SELECT title, description, event_type, start_at, end_at, location
            FROM campus_events
            WHERE {time_filter} {type_filter}
            ORDER BY start_at {'DESC' if asks_about_past else 'ASC'}, id
            LIMIT 5
        """)).mappings().all()

    if not rows:
        if type_filter:
            kind = "exam dates" if "exam" in type_filter else "deadlines"
            return f"There are no {kind} in the calendar yet. Ask your admin to add them."
        return "There are no upcoming campus events in the calendar yet. Ask your admin to add them."

    campus_timezone = timezone(timedelta(hours=5, minutes=30))
    entries = []
    for row in rows:
        start_at = row["start_at"]
        if start_at.tzinfo is not None:
            start_at = start_at.astimezone(campus_timezone)
        when = start_at.strftime("%d %b %Y, %I:%M %p")
        entry = f"{row['title']} — {when}"
        if row.get("location"):
            entry += f", {row['location']}"
        if row.get("description"):
            entry += f". {row['description'].strip()}"
        entries.append(entry)
    prefix = "Recent calendar items" if asks_about_past else "Upcoming calendar items"
    return prefix + ": " + "; ".join(entries) + "."
