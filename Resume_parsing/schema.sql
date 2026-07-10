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
