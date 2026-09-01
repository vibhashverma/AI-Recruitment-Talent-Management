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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    id SERIAL PRIMARY KEY,
                    job_title TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    location TEXT,
                    experience TEXT,
                    skills TEXT[],
                    education TEXT,
                    certification TEXT,
                    status TEXT DEFAULT 'Open',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
                    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
                    stage TEXT DEFAULT 'Applied',
                    recruiter_notes TEXT,
                    feedback TEXT,
                    interview_schedule TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE (candidate_id, job_id)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_questions (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
                    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
                    technical_questions TEXT,
                    behavioral_questions TEXT,
                    follow_up_questions TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE (candidate_id, job_id)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_reports (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
                    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
                    qa_transcript TEXT,
                    overall_score NUMERIC,
                    communication_feedback TEXT,
                    strengths TEXT,
                    improvements TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'candidate',
                    candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL,
                    is_active BOOLEAN DEFAULT TRUE,
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


# ---------------------------------------------------------------------------
# Job Postings
# ---------------------------------------------------------------------------

def insert_job(data: dict) -> dict:
    """Insert one job posting and return the stored row."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO job_postings
                    (job_title, company_name, location, experience,
                     skills, education, certification, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.get("job_title"),
                    data.get("company_name"),
                    data.get("location"),
                    data.get("experience"),
                    data.get("skills") or [],
                    data.get("education"),
                    data.get("certification"),
                    data.get("status") or "Open",
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_all_jobs(limit: int = 500):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM job_postings ORDER BY created_at DESC LIMIT %s;",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_job(job_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM job_postings WHERE id = %s;", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def update_job(job_id: int, data: dict):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE job_postings SET
                    job_title = %s,
                    company_name = %s,
                    location = %s,
                    experience = %s,
                    skills = %s,
                    education = %s,
                    certification = %s,
                    status = %s
                WHERE id = %s
                RETURNING *;
                """,
                (
                    data.get("job_title"),
                    data.get("company_name"),
                    data.get("location"),
                    data.get("experience"),
                    data.get("skills") or [],
                    data.get("education"),
                    data.get("certification"),
                    data.get("status") or "Open",
                    job_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def delete_job(job_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM job_postings WHERE id = %s;", (job_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Milestone 3 — Applications (ATS pipeline)
# ---------------------------------------------------------------------------

VALID_STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]


def upsert_application(candidate_id: int, job_id: int, stage: str = "Applied") -> dict:
    """Add a candidate to a job's pipeline. If already present, returns the
    existing row unchanged (does not overwrite stage/notes)."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO applications (candidate_id, job_id, stage)
                VALUES (%s, %s, %s)
                ON CONFLICT (candidate_id, job_id) DO NOTHING
                RETURNING *;
                """,
                (candidate_id, job_id, stage),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT * FROM applications WHERE candidate_id = %s AND job_id = %s;",
                    (candidate_id, job_id),
                )
                row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_applications(job_id: int = None, stage: str = None) -> list:
    """List applications, joined with candidate and job info for display."""
    query = """
        SELECT
            a.id, a.candidate_id, a.job_id, a.stage, a.recruiter_notes,
            a.feedback, a.interview_schedule, a.created_at, a.updated_at,
            c.full_name AS candidate_name, c.email AS candidate_email,
            c.skills AS candidate_skills,
            j.job_title, j.company_name
        FROM applications a
        JOIN candidates c ON c.id = a.candidate_id
        JOIN job_postings j ON j.id = a.job_id
        WHERE 1 = 1
    """
    params = []
    if job_id is not None:
        query += " AND a.job_id = %s"
        params.append(job_id)
    if stage is not None:
        query += " AND a.stage = %s"
        params.append(stage)
    query += " ORDER BY a.updated_at DESC;"

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]


def get_application(application_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM applications WHERE id = %s;", (application_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def update_application(application_id: int, data: dict):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE applications SET
                    stage = COALESCE(%s, stage),
                    recruiter_notes = COALESCE(%s, recruiter_notes),
                    feedback = COALESCE(%s, feedback),
                    interview_schedule = COALESCE(%s, interview_schedule),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (
                    data.get("stage"),
                    data.get("recruiter_notes"),
                    data.get("feedback"),
                    data.get("interview_schedule"),
                    application_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def delete_application(application_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE id = %s;", (application_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Milestone 3 — Interview Questions
# ---------------------------------------------------------------------------

def upsert_interview_questions(candidate_id: int, job_id: int, technical_json: str,
                                behavioral_json: str, follow_up_json: str) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO interview_questions
                    (candidate_id, job_id, technical_questions, behavioral_questions, follow_up_questions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id, job_id) DO UPDATE SET
                    technical_questions = EXCLUDED.technical_questions,
                    behavioral_questions = EXCLUDED.behavioral_questions,
                    follow_up_questions = EXCLUDED.follow_up_questions,
                    created_at = NOW()
                RETURNING *;
                """,
                (candidate_id, job_id, technical_json, behavioral_json, follow_up_json),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_interview_questions(candidate_id: int, job_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM interview_questions WHERE candidate_id = %s AND job_id = %s;",
                (candidate_id, job_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None


# ---------------------------------------------------------------------------
# Milestone 3 — Interview Reports (AI Interview Simulation)
# ---------------------------------------------------------------------------

def insert_interview_report(candidate_id: int, job_id: int, qa_transcript_json: str,
                             overall_score: float, communication_feedback: str,
                             strengths: str, improvements: str) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO interview_reports
                    (candidate_id, job_id, qa_transcript, overall_score,
                     communication_feedback, strengths, improvements)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (candidate_id, job_id, qa_transcript_json, overall_score,
                 communication_feedback, strengths, improvements),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_interview_reports(job_id: int = None, candidate_id: int = None) -> list:
    query = "SELECT * FROM interview_reports WHERE 1 = 1"
    params = []
    if job_id is not None:
        query += " AND job_id = %s"
        params.append(job_id)
    if candidate_id is not None:
        query += " AND candidate_id = %s"
        params.append(candidate_id)
    query += " ORDER BY created_at DESC;"

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Milestone 4 — Users (authentication & roles)
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password_hash: str, role: str = "candidate",
                 candidate_id: int = None) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, password_hash, role, candidate_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, email, role, candidate_id, is_active, created_at;
                """,
                (name, email, password_hash, role, candidate_id),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row)


def get_user_by_email(email: str):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s;", (email,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def link_candidate_to_user(user_id: int, candidate_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE users SET candidate_id = %s WHERE id = %s "
                "RETURNING id, name, email, role, candidate_id, is_active, created_at;",
                (candidate_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def list_users(role: str = None) -> list:
    query = "SELECT id, name, email, role, candidate_id, is_active, created_at FROM users"
    params = ()
    if role:
        query += " WHERE role = %s"
        params = (role,)
    query += " ORDER BY created_at DESC;"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def set_user_active(user_id: int, is_active: bool):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active = %s WHERE id = %s;", (is_active, user_id))
        conn.commit()


def update_user_role(user_id: int, role: str) -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE id = %s "
                "RETURNING id, name, email, role, candidate_id, is_active, created_at;",
                (role, user_id),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
