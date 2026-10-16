"""Idempotently load course entries transcribed from the user's screenshots.

Run from the project root with the project's Python environment:
    python .\database\seed_courses.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.main import engine


DATA = json.loads((PROJECT_ROOT / "data" / "campus_courses.json").read_text(encoding="utf-8"))


def main() -> None:
    inserted = 0
    updated = 0
    with engine.begin() as connection:
        for course in DATA["courses"]:
            existing_id = connection.execute(
                text("SELECT id FROM subjects WHERE code = :code ORDER BY id LIMIT 1"),
                {"code": course["code"]},
            ).scalar_one_or_none()
            values = {
                **course,
                "specialization_id": None,
            }
            if existing_id is None:
                connection.execute(
                    text("""
                        INSERT INTO subjects
                            (specialization_id, code, name, semester, term, instructor_name, section)
                        VALUES
                            (:specialization_id, :code, :name, :semester, :term, :instructor_name, :section)
                    """),
                    values,
                )
                inserted += 1
            else:
                connection.execute(
                    text("""
                        UPDATE subjects
                        SET name = :name, semester = :semester, term = :term,
                            instructor_name = :instructor_name, section = :section
                        WHERE id = :id
                    """),
                    {**values, "id": existing_id},
                )
                updated += 1
    print(f"Course catalog loaded: {inserted} added, {updated} updated.")


if __name__ == "__main__":
    main()
