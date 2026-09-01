"""
jobs_api.py
FastAPI microservice for managing Job Postings, backed by the same
PostgreSQL database as the Streamlit app.

Run with:
    uvicorn jobs_api:app --reload --port 8000
"""

from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

import db  # reuses get_connection / table setup from db.py
import matching  # Milestone 2: candidate-job matching, hiring score, skill-gap analysis

app = FastAPI(
    title="Recruitment Copilot - Job Postings API",
    description="CRUD API for job postings, used by the Streamlit front end.",
    version="1.0.0",
)

# Allow the Streamlit app (typically localhost:8501) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class JobPostingIn(BaseModel):
    job_title: str = Field(..., min_length=1)
    company_name: str = Field(..., min_length=1)
    location: Optional[str] = None
    experience: Optional[str] = None
    skills: List[str] = []
    education: Optional[str] = None
    certification: Optional[str] = None
    status: Optional[str] = "Open"


class JobPostingOut(JobPostingIn):
    id: int
    created_at: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Milestone 3 — ATS Pipeline schemas
# ---------------------------------------------------------------------------

class ApplicationIn(BaseModel):
    candidate_id: int
    job_id: int
    stage: Optional[str] = "Applied"


class ApplicationUpdate(BaseModel):
    stage: Optional[str] = None
    recruiter_notes: Optional[str] = None
    feedback: Optional[str] = None
    interview_schedule: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Startup: make sure tables exist
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    db.init_db()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobPostingOut, status_code=201)
def create_job(job: JobPostingIn):
    try:
        row = db.insert_job(job.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save job posting: {e}")
    row["created_at"] = str(row["created_at"])
    return row


@app.get("/jobs", response_model=List[JobPostingOut])
def list_jobs():
    rows = db.get_all_jobs()
    for r in rows:
        r["created_at"] = str(r["created_at"])
    return rows


@app.get("/jobs/{job_id}", response_model=JobPostingOut)
def get_job(job_id: int):
    row = db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job posting not found")
    row["created_at"] = str(row["created_at"])
    return row


@app.put("/jobs/{job_id}", response_model=JobPostingOut)
def update_job(job_id: int, job: JobPostingIn):
    existing = db.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job posting not found")
    row = db.update_job(job_id, job.model_dump())
    row["created_at"] = str(row["created_at"])
    return row


@app.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: int):
    existing = db.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job posting not found")
    db.delete_job(job_id)
    return None


# ---------------------------------------------------------------------------
# Milestone 2 — Matching & Skill Analysis
# ---------------------------------------------------------------------------

@app.get("/jobs/{job_id}/matches")
def get_job_matches(job_id: int):
    """Rank all candidates against a job posting: skill match, experience
    match, education match, overall hiring score, and skill-gap analysis."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found")

    candidates = db.get_all_candidates()
    if not candidates:
        return []

    try:
        return matching.rank_candidates_for_job(candidates, job)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {e}")


# ---------------------------------------------------------------------------
# Milestone 3 — ATS Integration for Candidate Management
# ---------------------------------------------------------------------------

@app.post("/applications", status_code=201)
def create_application(application: ApplicationIn):
    """Add a candidate to a job's recruitment pipeline (idempotent — safe to
    call again for the same candidate/job pair)."""
    job = db.get_job(application.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found")
    try:
        return db.upsert_application(application.candidate_id, application.job_id, application.stage or "Applied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add candidate to pipeline: {e}")


@app.get("/applications")
def list_applications(job_id: Optional[int] = None, stage: Optional[str] = None):
    """List pipeline entries, optionally filtered by job and/or stage."""
    return db.get_applications(job_id=job_id, stage=stage)


@app.get("/applications/{application_id}")
def get_application(application_id: int):
    row = db.get_application(application_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return row


@app.put("/applications/{application_id}")
def update_application(application_id: int, update: ApplicationUpdate):
    existing = db.get_application(application_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Application not found")

    if update.stage and update.stage not in db.VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage '{update.stage}'. Must be one of: {', '.join(db.VALID_STAGES)}",
        )

    payload = update.model_dump()
    if payload.get("interview_schedule") is not None:
        payload["interview_schedule"] = payload["interview_schedule"].isoformat()

    row = db.update_application(application_id, payload)
    return row


@app.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: int):
    existing = db.get_application(application_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete_application(application_id)
    return None
