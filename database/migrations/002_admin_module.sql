-- MCA CampusAI admin catalog migration (PostgreSQL)
--
-- Safe to apply to an existing MVP database: this migration preserves all
-- existing users and subjects. Existing subjects remain unlinked to a course
-- until an administrator associates them through the admin panel.
--
-- Run from the project root with psql connected to mca_campusai:
--   \i 'C:/Users/Preet/Desktop/MCA-campusAI/database/migrations/002_admin_module.sql'

BEGIN;

-- Academic departments. Existing course rows can remain without a department
-- until an administrator assigns one.
CREATE TABLE IF NOT EXISTS departments (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    code VARCHAR(40) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- A course is a program/catalog grouping (for example, MCA). Individual
-- semester subjects are stored in the existing subjects table.
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
);

-- Add the course relationship without changing or deleting existing subjects.
ALTER TABLE subjects
    ADD COLUMN IF NOT EXISTS course_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'subjects_course_id_fkey'
          AND conrelid = 'subjects'::regclass
    ) THEN
        ALTER TABLE subjects
            ADD CONSTRAINT subjects_course_id_fkey
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS subjects_course_id_idx ON subjects(course_id);

-- A subject may be taught by more than one faculty member, and faculty may
-- teach multiple subjects. The API will verify the selected user has role
-- 'faculty'; the FK keeps assignments attached to real accounts.
CREATE TABLE IF NOT EXISTS faculty_subject_assignments (
    id BIGSERIAL PRIMARY KEY,
    faculty_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    assigned_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT faculty_subject_assignments_unique UNIQUE (faculty_user_id, subject_id)
);

CREATE INDEX IF NOT EXISTS faculty_subject_assignments_subject_idx
    ON faculty_subject_assignments(subject_id);
CREATE INDEX IF NOT EXISTS faculty_subject_assignments_faculty_idx
    ON faculty_subject_assignments(faculty_user_id);

COMMIT;
