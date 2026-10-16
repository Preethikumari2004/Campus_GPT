from __future__ import annotations
from pwdlib import PasswordHash
from sqlalchemy import create_engine, text
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
password_hasher = PasswordHash.recommended()


def init_db() -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                full_name VARCHAR(120) NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL
                    CHECK (role IN ('student', 'faculty', 'admin')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS student_chat_conversations (
                id BIGSERIAL PRIMARY KEY,
                student_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(120) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS student_chat_turns (
                id BIGSERIAL PRIMARY KEY,
                conversation_id BIGINT NOT NULL REFERENCES student_chat_conversations(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS student_chat_conversations_owner_updated_idx ON student_chat_conversations(student_user_id, updated_at DESC)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS student_chat_turns_conversation_idx ON student_chat_turns(conversation_id, created_at)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id BIGSERIAL PRIMARY KEY,
                course_name VARCHAR(160) NOT NULL,
                session_date DATE NOT NULL,
                created_by BIGINT NOT NULL REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_records (
                id BIGSERIAL PRIMARY KEY,
                session_id BIGINT NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
                student_id BIGINT NOT NULL REFERENCES users(id),
                status VARCHAR(10) NOT NULL CHECK (status IN ('present', 'absent')),
                UNIQUE (session_id, student_id)
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS specializations (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS campus_events (
                id BIGSERIAL PRIMARY KEY,
                title VARCHAR(160) NOT NULL,
                description TEXT,
                event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('academic', 'exam', 'campus', 'deadline')),
                start_at TIMESTAMPTZ NOT NULL,
                end_at TIMESTAMPTZ,
                location VARCHAR(200),
                created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT campus_events_end_after_start CHECK (end_at IS NULL OR end_at >= start_at)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS campus_events_start_at_idx ON campus_events(start_at)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS subjects (
                id BIGSERIAL PRIMARY KEY,
                specialization_id BIGINT REFERENCES specializations(id) ON DELETE SET NULL,
                code VARCHAR(80) NOT NULL,
                name VARCHAR(160) NOT NULL,
                semester SMALLINT NOT NULL CHECK (semester BETWEEN 1 AND 6),
                term VARCHAR(40),
                instructor_name VARCHAR(120),
                section VARCHAR(40),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (specialization_id, code),
                UNIQUE (specialization_id, semester, name)
            )
        """))
        # Upgrade catalogs created by earlier MVP versions without discarding data.
        connection.execute(text("ALTER TABLE subjects ALTER COLUMN specialization_id DROP NOT NULL"))
        connection.execute(text("ALTER TABLE subjects ALTER COLUMN code TYPE VARCHAR(80)"))
        connection.execute(text("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS term VARCHAR(40)"))
        connection.execute(text("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS instructor_name VARCHAR(120)"))
        connection.execute(text("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS section VARCHAR(40)"))
        # Admin catalog schema (also represented by database/migrations/002_admin_module.sql).
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS departments (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                code VARCHAR(40) UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS courses (
                id BIGSERIAL PRIMARY KEY,
                department_id BIGINT REFERENCES departments(id) ON DELETE SET NULL,
                name VARCHAR(160) NOT NULL,
                code VARCHAR(80) NOT NULL UNIQUE,
                description TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT courses_name_department_unique UNIQUE (department_id, name)
            )
        """))
        connection.execute(text("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS course_id BIGINT"))
        connection.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'subjects_course_id_fkey'
                      AND conrelid = 'subjects'::regclass
                ) THEN
                    ALTER TABLE subjects ADD CONSTRAINT subjects_course_id_fkey
                        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE;
                END IF;
            END $$
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS subjects_course_id_idx ON subjects(course_id)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS faculty_subject_assignments (
                id BIGSERIAL PRIMARY KEY,
                faculty_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                assigned_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT faculty_subject_assignments_unique UNIQUE (faculty_user_id, subject_id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS faculty_subject_assignments_subject_idx ON faculty_subject_assignments(subject_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS faculty_subject_assignments_faculty_idx ON faculty_subject_assignments(faculty_user_id)"))
        connection.execute(text("ALTER TABLE attendance_sessions ADD COLUMN IF NOT EXISTS subject_id BIGINT REFERENCES subjects(id) ON DELETE CASCADE"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS attendance_sessions_faculty_date_idx ON attendance_sessions(created_by, session_date)"))
        connection.execute(text("""
            UPDATE attendance_sessions session
            SET subject_id = subject.id
            FROM faculty_subject_assignments assignment
            JOIN subjects subject ON subject.id = assignment.subject_id
            WHERE session.subject_id IS NULL
              AND assignment.faculty_user_id = session.created_by
              AND lower(subject.name) = lower(session.course_name)
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS student_subject_enrollments (
                id BIGSERIAL PRIMARY KEY,
                student_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                enrolled_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT student_subject_enrollments_unique UNIQUE (student_user_id, subject_id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS student_subject_enrollments_subject_idx ON student_subject_enrollments(subject_id)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS course_assignments (
                id BIGSERIAL PRIMARY KEY,
                subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                faculty_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(180) NOT NULL,
                instructions TEXT NOT NULL,
                due_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS course_assignments_subject_idx ON course_assignments(subject_id, due_at)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS assignment_submissions (
                id BIGSERIAL PRIMARY KEY,
                assignment_id BIGINT NOT NULL REFERENCES course_assignments(id) ON DELETE CASCADE,
                student_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                response_text TEXT NOT NULL,
                submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                score NUMERIC(5,2) CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
                feedback TEXT,
                reviewed_at TIMESTAMPTZ,
                CONSTRAINT assignment_submission_unique UNIQUE (assignment_id, student_user_id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS assignment_submissions_assignment_idx ON assignment_submissions(assignment_id)"))
        connection.execute(text("ALTER TABLE assignment_submissions ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(255)"))
        connection.execute(text("ALTER TABLE assignment_submissions ADD COLUMN IF NOT EXISTS attachment_key VARCHAR(80)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id BIGSERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                scope VARCHAR(20) NOT NULL CHECK (scope IN ('campus', 'faculty', 'course', 'private', 'submission')),
                subject_id BIGINT,
                uploaded_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT knowledge_document_scope_subject_check CHECK (
                    (scope IN ('course', 'submission') AND subject_id IS NOT NULL)
                    OR (scope IN ('campus', 'faculty', 'private') AND subject_id IS NULL)
                )
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS knowledge_documents_subject_idx ON knowledge_documents(subject_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS knowledge_documents_uploader_idx ON knowledge_documents(uploaded_by)"))
        # Campus documents remain available to CampusGPT for every role, while only
        # admins see their file listings.
        connection.execute(text("ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS knowledge_documents_scope_check"))
        connection.execute(text("ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS knowledge_document_scope_subject_check"))
        connection.execute(text("""
            UPDATE knowledge_documents d
            SET scope = 'campus'
            FROM users u
            WHERE d.uploaded_by = u.id AND u.role = 'admin' AND d.scope IN ('campus', 'faculty')
        """))
        connection.execute(text("""
            ALTER TABLE knowledge_documents
            ADD CONSTRAINT knowledge_documents_scope_check
            CHECK (scope IN ('campus', 'faculty', 'course', 'private', 'submission'))
        """))
        connection.execute(text("""
            ALTER TABLE knowledge_documents
            ADD CONSTRAINT knowledge_document_scope_subject_check
            CHECK (
                (scope IN ('course', 'submission') AND subject_id IS NOT NULL)
                OR (scope IN ('campus', 'faculty', 'private') AND subject_id IS NULL)
            )
        """))


def ensure_demo_accounts() -> None:
    default_accounts = [
        ("student_demo", "Demo Student", "student.demo@example.com", "student1234", "student"),
        ("faculty_demo", "Demo Faculty", "faculty.demo@example.com", "faculty1234", "faculty"),
        ("admin_demo", "Demo Admin", "admin.demo@example.com", "admin1234", "admin"),
    ]

    with engine.begin() as connection:
        for username, full_name, email, password, role in default_accounts:
            connection.execute(
                text("""
                    INSERT INTO users (username, email, full_name, password_hash, role)
                    VALUES (:username, :email, :full_name, :password_hash, :role)
                    ON CONFLICT (username) DO NOTHING
                """),
                {
                    "username": username,
                    "email": email,
                    "full_name": full_name,
                    "password_hash": password_hasher.hash(password),
                    "role": role,
                },
            )
