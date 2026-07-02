"""
Database Initialization Module.
Creates the SQLite database schema and seeds initial data for the FastMCP lab.
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "school.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    cohort TEXT NOT NULL,
    enrollment_year INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    credits INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    course_code TEXT NOT NULL,
    score REAL,
    grade TEXT,
    semester TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE
);
"""

SEED_SQL = """
INSERT OR IGNORE INTO students (student_id, name, email, cohort, enrollment_year) VALUES
    ('S1001', 'Alice Nguyen', 'alice.n@example.edu', 'A1', 2024),
    ('S1002', 'Bob Tran', 'bob.t@example.edu', 'A1', 2024),
    ('S1003', 'Charlie Le', 'charlie.l@example.edu', 'B1', 2023),
    ('S1004', 'Diana Pham', 'diana.p@example.edu', 'B1', 2023),
    ('S1005', 'Ethan Vu', 'ethan.v@example.edu', 'C1', 2022),
    ('S1006', 'Fiona Hoang', 'fiona.h@example.edu', 'C1', 2022),
    ('S1007', 'George Dang', 'george.d@example.edu', 'A1', 2024),
    ('S1008', 'Hannah Bui', 'hannah.b@example.edu', 'B1', 2023);

INSERT OR IGNORE INTO courses (course_code, title, department, credits) VALUES
    ('CS101', 'Introduction to Computer Science', 'Computer Science', 3),
    ('CS201', 'Data Structures and Algorithms', 'Computer Science', 4),
    ('AI301', 'Artificial Intelligence & Machine Learning', 'AI Engineering', 4),
    ('DB202', 'Database Systems and SQL', 'Computer Science', 3),
    ('MA101', 'Calculus I', 'Mathematics', 3);

INSERT OR IGNORE INTO enrollments (student_id, course_code, score, grade, semester) VALUES
    ('S1001', 'CS101', 92.5, 'A', 'Fall 2024'),
    ('S1001', 'DB202', 88.0, 'B+', 'Fall 2024'),
    ('S1002', 'CS101', 78.0, 'B-', 'Fall 2024'),
    ('S1002', 'DB202', 85.5, 'B', 'Fall 2024'),
    ('S1003', 'CS201', 95.0, 'A+', 'Spring 2024'),
    ('S1003', 'AI301', 89.0, 'B+', 'Spring 2024'),
    ('S1004', 'CS201', 72.0, 'C+', 'Spring 2024'),
    ('S1004', 'AI301', 91.0, 'A', 'Spring 2024'),
    ('S1005', 'AI301', 98.0, 'A+', 'Fall 2023'),
    ('S1005', 'MA101', 84.0, 'B', 'Fall 2023'),
    ('S1006', 'AI301', 68.5, 'C', 'Fall 2023'),
    ('S1007', 'CS101', 88.5, 'B+', 'Fall 2024'),
    ('S1008', 'DB202', 94.0, 'A', 'Spring 2024');
"""


def create_database(db_path: str | Path | None = None, force_recreate: bool = False) -> Path:
    """
    Creates and initializes the SQLite database with schema and seed data.

    Args:
        db_path: Path to the SQLite database file. Defaults to DEFAULT_DB_PATH.
        force_recreate: If True, deletes existing database file before initializing.

    Returns:
        Path object representing the database location.
    """
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if force_recreate and target_path.exists():
        try:
            target_path.unlink()
        except OSError as e:
            print(f"Warning: Could not remove existing database {target_path}: {e}")

    conn = sqlite3.connect(target_path)
    try:
        cursor = conn.cursor()
        cursor.executescript(SCHEMA_SQL)
        cursor.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()

    return target_path


if __name__ == "__main__":
    db_loc = create_database(force_recreate=True)
    print(f"Database successfully initialized at: {db_loc}")
