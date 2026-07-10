"""
db.py
PostgreSQL data access layer for the Resume Parsing & Candidate Profiling app.
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "recruitment_copilot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}


@contextmanager
def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create the candidates table if it doesn't exist yet."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    id SERIAL PRIMARY KEY,
                    full_name TEXT,
                    email TEXT,
                    phone TEXT,
                    location TEXT,
                    education TEXT,
                    experience_years TEXT,
                    experience_details TEXT,
                    skills TEXT[],
                    certifications TEXT,
                    projects TEXT,
                    raw_text TEXT,
                    source_filename TEXT,
                    status TEXT DEFAULT 'Processed',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
        conn.commit()


def insert_candidate(data: dict, source_filename: str, raw_text: str) -> dict:
    """Insert one parsed candidate and return the stored row."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO candidates
                    (full_name, email, phone, location, education,
                     experience_years, experience_details, skills,
                     certifications, projects, raw_text, source_filename, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.get("full_name"),
                    data.get("email"),
                    data.get("phone"),
                    data.get("location"),
                    data.get("education"),
                    data.get("experience_years"),
                    data.get("experience_details"),
                    data.get("skills") or [],
                    data.get("certifications"),
                    data.get("projects"),
                    raw_text,
                    source_filename,
                    "Processed",
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_all_candidates(limit: int = 500):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM candidates ORDER BY created_at DESC LIMIT %s;",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_dashboard_stats():
    """Return counts used on the Dashboard / Resume Upload metric cards."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM candidates;")
            total = cur.fetchone()[0]
    return {
        "resumes_processed": total,
        "profiles_created": total,
    }


def delete_candidate(candidate_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM candidates WHERE id = %s;", (candidate_id,))
        conn.commit()
