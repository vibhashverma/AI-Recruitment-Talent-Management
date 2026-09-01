-- Run once against your PostgreSQL database, e.g.:
--   createdb recruitment_copilot
--   psql -d recruitment_copilot -f schema.sql
-- (the app also creates this automatically on first run via db.init_db())

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

CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates (email);

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

CREATE INDEX IF NOT EXISTS idx_job_postings_title ON job_postings (job_title);

-- ---------------------------------------------------------------------------
-- Milestone 3 — AI Interview & Candidate Management
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
    stage TEXT DEFAULT 'Applied',            -- Applied, Screening, Interview, Selected, Rejected
    recruiter_notes TEXT,
    feedback TEXT,
    interview_schedule TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE TABLE IF NOT EXISTS interview_questions (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
    technical_questions TEXT,   -- JSON array, stored as text
    behavioral_questions TEXT,  -- JSON array, stored as text
    follow_up_questions TEXT,   -- JSON array, stored as text
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE TABLE IF NOT EXISTS interview_reports (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES job_postings(id) ON DELETE CASCADE,
    qa_transcript TEXT,              -- JSON array, stored as text
    overall_score NUMERIC,
    communication_feedback TEXT,
    strengths TEXT,
    improvements TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_applications_job ON applications (job_id);
CREATE INDEX IF NOT EXISTS idx_applications_candidate ON applications (candidate_id);

-- ---------------------------------------------------------------------------
-- Milestone 4 — Authentication & Roles
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'candidate',   -- 'candidate' | 'recruiter' | 'admin'
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
