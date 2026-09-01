"""
app.py
Recruitment Copilot — Milestone 4: Role-Based Dashboards, Auth & Deployment.

Run with:  streamlit run app.py
"""

import json
import os
from collections import Counter
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

JOBS_API_URL = os.getenv("JOBS_API_URL", "http://localhost:8000")

from db import (
    delete_candidate,
    get_all_candidates,
    get_dashboard_stats,
    init_db,
    insert_candidate,
)
from gemini_extractor import extract_candidate_data
from resume_parser import extract_text
import db as db_module
import interview_ai
import auth



st.set_page_config(
    page_title="Ai Recruitment",
    page_icon="🧭",
    layout="wide",
)

# ---------------------------------------------------------------------------
# One-time setup
# ---------------------------------------------------------------------------
if "db_ready" not in st.session_state:
    try:
        init_db()
        st.session_state.db_ready = True
    except Exception as e:
        st.session_state.db_ready = False
        st.session_state.db_error = str(e)

# ---------------------------------------------------------------------------
# DB connection guard — nothing else (including login) works without this
# ---------------------------------------------------------------------------
if not st.session_state.db_ready:
    st.error(
        "Could not connect to PostgreSQL. Check your DB settings in `.env`.\n\n"
        f"Details: {st.session_state.get('db_error')}"
    )
    st.stop()

try:
    auth.ensure_admin_bootstrapped()
except Exception:
    pass  # ADMIN_EMAIL / ADMIN_PASSWORD not set, or already bootstrapped — non-fatal

# ---------------------------------------------------------------------------
# Login / signup gate
# ---------------------------------------------------------------------------
if not auth.render_auth_gate():
    st.stop()

current_user = auth.current_user()
user_role = current_user["role"]  # 'candidate' | 'recruiter' | 'admin'

if "last_extracted" not in st.session_state:
    st.session_state.last_extracted = None
if "last_filename" not in st.session_state:
    st.session_state.last_filename = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def metric_card(label, value, sublabel=None):
    st.metric(label, value)
    if sublabel:
        st.caption(sublabel)


def render_job_card(job: dict):
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Company:** {job.get('company_name') or '—'}")
        st.write(f"**Location:** {job.get('location') or '—'}")
        st.write(f"**Experience:** {job.get('experience') or '—'}")
    with c2:
        st.write(f"**Education:** {job.get('education') or '—'}")
        st.write(f"**Certification:** {job.get('certification') or '—'}")
        st.write(f"**Status:** {job.get('status') or '—'}")

    skills = job.get("skills") or []
    if skills:
        st.write("**Skills:**")
        st.markdown(" ".join(f"`{s}`" for s in skills))


def render_candidate_card(data: dict):
    st.markdown("**Extracted Information**")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Name:** {data.get('full_name') or '—'}")
        st.write(f"**Email:** {data.get('email') or '—'}")
        st.write(f"**Phone:** {data.get('phone') or '—'}")
    with c2:
        st.write(f"**Location:** {data.get('location') or '—'}")
        st.write(f"**Education:** {data.get('education') or '—'}")
        st.write(f"**Experience:** {data.get('experience_years') or '—'}")

    skills = data.get("skills") or []
    if skills:
        st.write("**Skills:**")
        st.markdown(
            " ".join(f"`{s}`" for s in skills),
        )

    if data.get("experience_details"):
            st.markdown("Experience details")
            st.write(data["experience_details"])

    if data.get("projects"):
            st.markdown("Projects")
            st.write(data["projects"])

    if data.get("certifications"):
            st.markdown("Certifications")
            st.write(data["certifications"])


MAX_SIMULATION_QUESTIONS = 3  # keep mock interviews short


def render_interview_questions(questions: dict):
    """Render a generated question set: technical (by difficulty), behavioural, follow-up."""
    st.markdown("#### 🧠 Technical Questions")
    for level in ["Beginner", "Intermediate", "Advanced"]:
        level_qs = [q for q in questions.get("technical_questions", []) if q.get("difficulty") == level]
        if level_qs:
            st.markdown(f"**{level}**")
            for q in level_qs:
                st.write(f"- {q.get('question')}")

    st.markdown("#### 🤝 Behavioural Questions")
    for q in questions.get("behavioral_questions", []):
        difficulty = q.get("difficulty", "")
        st.write(f"- {q.get('question')}" + (f"  `{difficulty}`" if difficulty else ""))

    st.markdown("#### 🔍 Follow-up Questions (based on your skills)")
    for q in questions.get("follow_up_questions", []):
        skill = q.get("based_on_skill", "")
        st.write(f"- {q.get('question')}" + (f"  _(re: {skill})_" if skill else ""))


def render_interview_simulation(sim_job: dict, sim_candidate: dict, session_key: str, allow_voice: bool = False):
    """Shared Q&A simulation flow used by both the recruiter's Interview
    Simulation page and a candidate's self-service My Interview page.
    Capped at MAX_SIMULATION_QUESTIONS questions total (technical + behavioural)."""

    if st.button("▶️ Start / Restart Simulation", type="primary", key=f"start_{session_key}"):
        existing_q = db_module.get_interview_questions(sim_candidate["id"], sim_job["id"])
        if not existing_q:
            with st.spinner("No saved questions found — generating with Gemini..."):
                try:
                    generated = interview_ai.generate_interview_questions(sim_job, sim_candidate)
                    db_module.upsert_interview_questions(
                        sim_candidate["id"], sim_job["id"],
                        json.dumps(generated.get("technical_questions", [])),
                        json.dumps(generated.get("behavioral_questions", [])),
                        json.dumps(generated.get("follow_up_questions", [])),
                    )
                    tech_qs = generated.get("technical_questions", [])
                    behav_qs = generated.get("behavioral_questions", [])
                except Exception as e:
                    st.error(f"Failed to generate interview questions: {e}")
                    tech_qs, behav_qs = [], []
        else:
            tech_qs = json.loads(existing_q["technical_questions"] or "[]")
            behav_qs = json.loads(existing_q["behavioral_questions"] or "[]")

        all_questions = ([q["question"] for q in tech_qs] + [q["question"] for q in behav_qs])[:MAX_SIMULATION_QUESTIONS]
        st.session_state[session_key] = {
            "questions": all_questions,
            "current_index": 0,
            "transcript": [],
            "report": None,
        }
        st.rerun()

    sim_state = st.session_state.get(session_key)
    if not sim_state or not sim_state["questions"]:
        return

    idx = sim_state["current_index"]
    total = len(sim_state["questions"])

    if sim_state["report"] is not None:
        report = sim_state["report"]
        st.markdown("### 📊 Interview Performance Report")
        st.metric("Overall Score", f"{report['overall_score']}%")
        st.write(f"**Communication Feedback:** {report['communication_feedback']}")
        st.write(f"**Strengths:** {report['strengths']}")
        st.write(f"**Areas to Improve:** {report['improvements']}")

        st.markdown("#### Full Transcript")
        for i, item in enumerate(sim_state["transcript"], start=1):
            with st.expander(f"Q{i}: {item['question'][:80]}"):
                st.write(f"**Response:** {item['response'] or '_(skipped)_'}")
                st.write(f"**Relevance Score:** {item['relevance_score']}%")
                st.write(f"**Feedback:** {item['communication_feedback']}")

    elif idx < total:
        st.progress(idx / total, text=f"Question {idx + 1} of {total}")
        current_q = sim_state["questions"][idx]
        st.markdown(f"### {current_q}")

        response_key = f"response_{session_key}_{idx}"
        transcript_key = f"voice_transcript_{session_key}_{idx}"

        if allow_voice:
            try:
                from streamlit_mic_recorder import mic_recorder
                st.caption("🎤 Answer by voice, or type below.")
                audio = mic_recorder(start_prompt="🎤 Start Recording", stop_prompt="⏹️ Stop", key=f"mic_{session_key}_{idx}")
                if audio and audio.get("bytes"):
                    st.audio(audio["bytes"])  # confirms the mic actually captured something
                    with st.spinner("Transcribing your answer..."):
                        try:
                            transcript = interview_ai.transcribe_audio(audio["bytes"])
                            if transcript:
                                st.session_state[transcript_key] = transcript
                                st.success("Transcribed — check the text box below and edit if needed.")
                            else:
                                st.warning("Got an empty transcript — please type your answer instead.")
                        except Exception as e:
                            st.warning("Voice transcription failed — please type your answer instead.")
                            with st.expander("Show error details"):
                                st.caption(str(e))
            except ImportError:
                st.caption("Voice input needs the `streamlit-mic-recorder` package (see requirements.txt).")

        response_text = st.text_area(
            "Your response",
            value=st.session_state.get(transcript_key, ""),
            key=response_key,
            height=150,
        )

        if st.button("✅ Submit & Evaluate", type="primary", key=f"submit_{session_key}_{idx}"):
            with st.spinner("Evaluating your response with Gemini..."):
                try:
                    evaluation = interview_ai.evaluate_interview_response(current_q, response_text, sim_job)
                    sim_state["transcript"].append({
                        "question": current_q,
                        "response": response_text,
                        "relevance_score": evaluation["relevance_score"],
                        "communication_feedback": evaluation["communication_feedback"],
                        "strengths": evaluation["strengths"],
                        "improvements": evaluation["improvements"],
                    })
                    sim_state["current_index"] += 1
                    st.session_state[session_key] = sim_state
                    st.rerun()
                except Exception as e:
                    st.error(f"Evaluation failed: {e}")

        if sim_state["transcript"]:
            last = sim_state["transcript"][-1]
            st.caption(f"Last answer — Relevance: {last['relevance_score']}%  •  {last['communication_feedback']}")

    else:
        st.success("All questions answered.")
        if st.button("📊 Generate Performance Report", type="primary", key=f"report_{session_key}"):
            with st.spinner("Summarizing the interview with Gemini..."):
                try:
                    report = interview_ai.generate_performance_report(sim_state["transcript"], sim_job)
                    db_module.insert_interview_report(
                        sim_candidate["id"], sim_job["id"],
                        json.dumps(sim_state["transcript"]),
                        report["overall_score"],
                        report["communication_feedback"],
                        report["strengths"],
                        report["improvements"],
                    )
                    sim_state["report"] = report
                    st.session_state[session_key] = sim_state
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to generate report: {e}")


# ---------------------------------------------------------------------------
# Sidebar navigation — role-aware
# ---------------------------------------------------------------------------
RECRUITER_PAGES = [
    "Dashboard",
    "Resume Upload",
    "Candidates",
    "Job Postings",
    "Candidate Matching",
    "Candidate Pipeline",
    "Interview Simulation",
    "Analytics",
]
CANDIDATE_PAGES = [
    "My Dashboard",
    "My Profile",
    "Job Openings",
    "Interview Prep",
    "My Interview",
]
ADMIN_PAGES = ["Admin Dashboard"]

with st.sidebar:
    st.markdown("##  Recruitment Copilot")
    st.caption(f"👤 {current_user['name']}  •  _{user_role}_")
    if st.button("Log Out", use_container_width=True):
        auth.logout()

    if user_role == "admin":
        nav_options = ADMIN_PAGES + RECRUITER_PAGES
    elif user_role == "recruiter":
        nav_options = RECRUITER_PAGES
    else:
        nav_options = CANDIDATE_PAGES

    page = st.radio("Navigate", nav_options, label_visibility="collapsed")
    st.markdown("---")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
if page == "Dashboard":
    st.title("Dashboard")
    stats = get_dashboard_stats()
    candidates = get_all_candidates()

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Resumes Processed", stats["resumes_processed"])
    with c2:
        metric_card("Profiles Created", stats["profiles_created"])
    #with c3:
        #metric_card("Extraction Accuracy", "97%" if candidates else "—")

    # -----------------------------------------------------------------
    # Milestone 4, Module 1 — recruitment pipeline metrics
    # -----------------------------------------------------------------
    st.markdown("### Recruitment Pipeline")

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=5)
        jobs_resp.raise_for_status()
        dash_jobs = jobs_resp.json()
    except Exception:
        dash_jobs = []

    try:
        all_apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=5)
        all_apps_resp.raise_for_status()
        all_applications = all_apps_resp.json()
    except Exception:
        all_applications = []

    open_jobs = [j for j in dash_jobs if (j.get("status") or "Open") == "Open"]
    stage_counts = Counter(a["stage"] for a in all_applications)
    shortlisted = sum(stage_counts.get(s, 0) for s in ["Screening", "Interview", "Selected"])
    interviews_scheduled = sum(1 for a in all_applications if a.get("interview_schedule"))

    # Optimization (Milestone 4, Module 4): cap how many jobs we run the
    # matching engine against for this summary metric, so the dashboard
    # doesn't fan out to every open job on every render.
    avg_hiring_score = None
    sample_jobs = open_jobs[:5]
    if sample_jobs:
        all_scores = []
        for j in sample_jobs:
            try:
                m_resp = requests.get(f"{JOBS_API_URL}/jobs/{j['id']}/matches", timeout=10)
                m_resp.raise_for_status()
                all_scores.extend(r["hiring_score"] for r in m_resp.json())
            except Exception:
                continue
        if all_scores:
            avg_hiring_score = round(sum(all_scores) / len(all_scores), 1)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Candidates", len(candidates))
    m2.metric("Total Job Openings", len(open_jobs))
    m3.metric("Candidates Shortlisted", shortlisted)
    m4.metric("Interviews Scheduled", interviews_scheduled)

    m5, m6, m7 = st.columns(3)
    m5.metric("Selected Candidates", stage_counts.get("Selected", 0))
    m6.metric("Rejected Candidates", stage_counts.get("Rejected", 0))
    m7.metric("Avg. Hiring Score", f"{avg_hiring_score}%" if avg_hiring_score is not None else "—")

    st.markdown("#### Candidate Pipeline")
    if all_applications:
        pipeline_order = ["Applied", "Screening", "Interview", "Selected", "Rejected"]
        funnel_counts = [stage_counts.get(s, 0) for s in pipeline_order]
        fig_funnel = px.funnel(x=funnel_counts, y=pipeline_order)
        fig_funnel.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_funnel, use_container_width=True)
    else:
        st.caption("No candidates in any pipeline yet. Add candidates to a job's pipeline from **Candidate Matching**.")

    st.markdown("### Overview")

    pie1, pie2 = st.columns(2)

    with pie1:
        st.markdown("#### Job Postings by Status")
        if dash_jobs:
            status_counts = Counter((j.get("status") or "Open") for j in dash_jobs)
            fig_status = px.pie(
                names=list(status_counts.keys()),
                values=list(status_counts.values()),
                hole=0.45,
            )
            fig_status.update_traces(textinfo="label+percent")
            fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.caption("No job postings yet.")

    with pie2:
        st.markdown("#### Top Skills Across Candidates")
        if candidates:
            skill_counter = Counter()
            for c in candidates:
                for s in (c["skills"] or []):
                    skill_counter[s] += 1

            if skill_counter:
                top_skills = skill_counter.most_common(6)
                other_count = sum(skill_counter.values()) - sum(v for _, v in top_skills)
                labels = [s for s, _ in top_skills]
                values = [v for _, v in top_skills]
                if other_count > 0:
                    labels.append("Others")
                    values.append(other_count)

                fig_skills = px.pie(names=labels, values=values, hole=0.45)
                fig_skills.update_traces(textinfo="label+percent")
                fig_skills.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
                st.plotly_chart(fig_skills, use_container_width=True)
            else:
                st.caption("No skill data yet.")
        else:
            st.caption("No candidates yet.")

    st.markdown("### Recently Processed Candidates")
    if candidates:
        rows = [
            {
                "Candidate Name": c["full_name"] or "—",
                "Email": c["email"] or "—",
                "Experience": c["experience_years"] or "—",
                "Status": c["status"],
            }
            for c in candidates[:10]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No candidates processed yet. Head to **Resume Upload** to get started.")

# ---------------------------------------------------------------------------
# Resume Upload
# ---------------------------------------------------------------------------
elif page == "Resume Upload":
    st.title("Resume Parsing & Candidate Profiling")
    st.caption("Upload and process resumes to create structured candidate profiles")

    stats = get_dashboard_stats()
    candidates = get_all_candidates()

    m1, m2, m3 = st.columns(3)
    m1.metric("Resumes Processed", stats["resumes_processed"])
    #m2.metric("Extraction Accuracy", "97%" if candidates else "—")
    m3.metric("Profiles Created", stats["profiles_created"])

    st.markdown("---")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("#### Upload Resume")
        uploaded_file = st.file_uploader(
            "Drag and drop resume or click to browse",
            type=["pdf", "docx"],
            help="Supported formats: PDF, DOCX",
        )

        if uploaded_file is not None:
            process = st.button("⚙️ Process Resume", type="primary", use_container_width=True)

            if process:
                with st.spinner("Extracting text from document..."):
                    try:
                        file_bytes = uploaded_file.getvalue()
                        raw_text = extract_text(uploaded_file.name, file_bytes)
                    except Exception as e:
                        st.error(f"Failed to read file: {e}")
                        st.stop()

                with st.spinner("Extracting structured profile with Gemini..."):
                    try:
                        data = extract_candidate_data(raw_text)
                    except Exception as e:
                        st.error(f"Failed to extract candidate data: {e}")
                        st.stop()

                with st.spinner("Saving to database..."):
                    try:
                        saved = insert_candidate(data, uploaded_file.name, raw_text)
                    except Exception as e:
                        st.error(f"Failed to save candidate: {e}")
                        st.stop()

                st.session_state.last_extracted = saved
                st.session_state.last_filename = uploaded_file.name
                st.success(f"Processed {uploaded_file.name} successfully.")
                st.rerun()

    with right:
        if st.session_state.last_extracted:
            render_candidate_card(st.session_state.last_extracted)
        else:
            st.info("Upload and process a resume to see the extracted profile here.")

    st.markdown("---")
    st.markdown("#### Recently Processed Candidates")
    if candidates:
        rows = [
            {
                "Candidate Name": c["full_name"] or "—",
                "Email": c["email"] or "—",
                "Experience": c["experience_years"] or "—",
                "Status": c["status"],
            }
            for c in candidates[:10]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No resumes processed yet.")

# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
elif page == "Candidates":
    st.title("Candidates")
    candidates = get_all_candidates()

    if not candidates:
        st.info("No candidates yet. Upload a resume from the **Resume Upload** page.")
    else:
        search = st.text_input("Search by name, email, or skill")

        filtered = candidates
        if search:
            s = search.lower()
            filtered = [
                c for c in candidates
                if s in (c["full_name"] or "").lower()
                or s in (c["email"] or "").lower()
                or any(s in sk.lower() for sk in (c["skills"] or []))
            ]

        for c in filtered:
            with st.expander(f"{c['full_name'] or 'Unknown'} — {c['email'] or 'no email'}"):
                render_candidate_card(c)
                col1, col2 = st.columns([1, 5])
                with col1:
                    if st.button("Delete", key=f"del_{c['id']}"):
                        delete_candidate(c["id"])
                        st.rerun()

# ---------------------------------------------------------------------------
# Placeholder pages for future milestones
# ---------------------------------------------------------------------------
elif page == "Job Postings":
    st.title("Job Postings")
    st.caption("Create and manage job postings (stored via the Jobs API / PostgreSQL)")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("#### New Job Posting")
        with st.form("job_posting_form", clear_on_submit=True):
            job_title = st.text_input("Job Title *")
            company_name = st.text_input("Company Name *")
            location = st.text_input("Location")
            experience = st.text_input("Experience (e.g. '3-5 years')")
            skills_raw = st.text_input("Skills (comma-separated)")
            education = st.text_input("Education")
            certification = st.text_input("Certification")
            status = st.selectbox("Status", ["Open", "On Hold", "Closed"])

            submitted = st.form_submit_button("➕ Add Job Posting", type="primary", use_container_width=True)

            if submitted:
                if not job_title or not company_name:
                    st.error("Job Title and Company Name are required.")
                else:
                    payload = {
                        "job_title": job_title,
                        "company_name": company_name,
                        "location": location or None,
                        "experience": experience or None,
                        "skills": [s.strip() for s in skills_raw.split(",") if s.strip()],
                        "education": education or None,
                        "certification": certification or None,
                        "status": status,
                    }
                    try:
                        resp = requests.post(f"{JOBS_API_URL}/jobs", json=payload, timeout=10)
                        resp.raise_for_status()
                        st.success(f"Job posting '{job_title}' created.")
                        st.rerun()
                    except requests.exceptions.ConnectionError:
                        st.error(
                            f"Could not reach the Jobs API at {JOBS_API_URL}. "
                            "Make sure it's running: `uvicorn jobs_api:app --reload --port 8000`"
                        )
                    except requests.exceptions.HTTPError:
                        st.error(f"Jobs API error: {resp.text}")
                    except Exception as e:
                        st.error(f"Failed to create job posting: {e}")

    with right:
        st.markdown("#### Existing Postings")
        try:
            resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
            resp.raise_for_status()
            jobs = resp.json()
        except requests.exceptions.ConnectionError:
            jobs = None
            st.warning(
                f"Could not reach the Jobs API at {JOBS_API_URL}. "
                "Start it with: `uvicorn jobs_api:app --reload --port 8000`"
            )
        except Exception as e:
            jobs = None
            st.error(f"Failed to load job postings: {e}")

        if jobs:
            if "editing_job_id" not in st.session_state:
                st.session_state.editing_job_id = None

            for job in jobs:
                with st.expander(f"{job['job_title']} — {job['company_name']}"):
                    if st.session_state.editing_job_id == job["id"]:
                        st.markdown("**Update Job Posting**")
                        with st.form(f"edit_job_form_{job['id']}"):
                            e_job_title = st.text_input("Job Title *", value=job["job_title"])
                            e_company_name = st.text_input("Company Name *", value=job["company_name"])
                            e_location = st.text_input("Location", value=job.get("location") or "")
                            e_experience = st.text_input("Experience", value=job.get("experience") or "")
                            e_skills_raw = st.text_input(
                                "Skills (comma-separated)",
                                value=", ".join(job.get("skills") or []),
                            )
                            e_education = st.text_input("Education", value=job.get("education") or "")
                            e_certification = st.text_input("Certification", value=job.get("certification") or "")
                            status_options = ["Open", "On Hold", "Closed"]
                            current_status = job.get("status") or "Open"
                            e_status = st.selectbox(
                                "Status", status_options,
                                index=status_options.index(current_status) if current_status in status_options else 0,
                            )

                            save_col, cancel_col = st.columns(2)
                            with save_col:
                                save_clicked = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
                            with cancel_col:
                                cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)

                        if save_clicked:
                            if not e_job_title or not e_company_name:
                                st.error("Job Title and Company Name are required.")
                            else:
                                update_payload = {
                                    "job_title": e_job_title,
                                    "company_name": e_company_name,
                                    "location": e_location or None,
                                    "experience": e_experience or None,
                                    "skills": [s.strip() for s in e_skills_raw.split(",") if s.strip()],
                                    "education": e_education or None,
                                    "certification": e_certification or None,
                                    "status": e_status,
                                }
                                try:
                                    resp = requests.put(f"{JOBS_API_URL}/jobs/{job['id']}", json=update_payload, timeout=10)
                                    resp.raise_for_status()
                                    st.success("Job posting updated.")
                                    st.session_state.editing_job_id = None
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to update job posting: {e}")
                        if cancel_clicked:
                            st.session_state.editing_job_id = None
                            st.rerun()
                    else:
                        render_job_card(job)
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("✏️ Edit", key=f"edit_job_{job['id']}", use_container_width=True):
                                st.session_state.editing_job_id = job["id"]
                                st.rerun()
                        with b2:
                            if st.button("🗑️ Delete", key=f"del_job_{job['id']}", use_container_width=True):
                                try:
                                    requests.delete(f"{JOBS_API_URL}/jobs/{job['id']}", timeout=10)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to delete: {e}")
        elif jobs is not None:
            st.info("No job postings yet. Add one on the left.")

# ---------------------------------------------------------------------------
# Candidate Matching (Milestone 2)
# ---------------------------------------------------------------------------
elif page == "Candidate Matching":
    st.title("Candidate Matching & Hiring Score")
    st.caption("Match candidates against a job posting, rank them by hiring score, and review skill gaps.")

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        jobs = jobs_resp.json()
    except requests.exceptions.ConnectionError:
        jobs = None
        st.warning(
            f"Could not reach the Jobs API at {JOBS_API_URL}. "
            "Start it with: `uvicorn jobs_api:app --reload --port 8000`"
        )
    except Exception as e:
        jobs = None
        st.error(f"Failed to load job postings: {e}")

    if jobs is not None:
        if not jobs:
            st.info("No job postings yet. Add one on the **Job Postings** page first.")
        else:
            job_labels = {f"{j['job_title']} — {j['company_name']} (#{j['id']})": j["id"] for j in jobs}
            selected_label = st.selectbox("Select a job posting", list(job_labels.keys()))
            selected_job_id = job_labels[selected_label]

            if st.button("🔍 Run Matching", type="primary"):
                with st.spinner("Scoring candidates against this job..."):
                    try:
                        resp = requests.get(f"{JOBS_API_URL}/jobs/{selected_job_id}/matches", timeout=30)
                        resp.raise_for_status()
                        st.session_state.match_results = resp.json()
                        st.session_state.match_job_label = selected_label
                    except Exception as e:
                        st.error(f"Matching failed: {e}")
                        st.session_state.match_results = None

            results = st.session_state.get("match_results")
            if results is not None:
                st.markdown(f"### Results for: {st.session_state.get('match_job_label')}")

                if not results:
                    st.info("No candidates in the system yet. Process resumes from **Resume Upload** first.")
                else:
                    st.markdown("#### Candidate Ranking")

                    fc1, fc2 = st.columns([2, 1])
                    with fc1:
                        search_text = st.text_input(
                            "Filter by candidate name or skill",
                            key="match_filter_text",
                            placeholder="e.g. 'python' or a candidate name",
                        )
                    with fc2:
                        sort_option = st.selectbox(
                            "Sort by",
                            ["Top Ranker", "Top 10", "Ascending", "Descending"],
                            key="match_sort_option",
                        )

                    view_results = results
                    if search_text:
                        s = search_text.strip().lower()
                        view_results = [
                            r for r in view_results
                            if s in (r["full_name"] or "").lower()
                            or any(
                                s in sk.lower()
                                for sk in (r["matched_skills"] + r["missing_skills"] + r["additional_skills"])
                            )
                        ]

                    if sort_option == "Ascending":
                        view_results = sorted(view_results, key=lambda r: r["hiring_score"])
                    elif sort_option == "Descending":
                        view_results = sorted(view_results, key=lambda r: r["hiring_score"], reverse=True)
                    elif sort_option == "Top 10":
                        view_results = sorted(view_results, key=lambda r: r["hiring_score"], reverse=True)[:10]
                    else:  # "Top Ranker" — full ranked list, best first
                        view_results = sorted(view_results, key=lambda r: r["hiring_score"], reverse=True)

                    if not view_results:
                        st.info("No candidates match this filter.")
                    else:
                        chart_data = {
                            (r["full_name"] or f"Candidate {r['candidate_id']}"): r["hiring_score"]
                            for r in view_results
                        }
                        st.bar_chart(chart_data)

                        for rank, r in enumerate(view_results, start=1):
                            header = f"#{rank} — {r['full_name'] or 'Unknown'} — Hiring Score: {r['hiring_score']}%"
                            with st.expander(header):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Hiring Score", f"{r['hiring_score']}%")
                                c2.metric("Skill Match", f"{r['skill_match_pct']}%")
                                c3.metric("Skill Gap", f"{r['skill_gap_pct']}%")

                                st.caption(
                                    f"Skill (60%): {r['skill_match_pct']}%  •  "
                                    f"Experience (25%): {r['experience_match_score']}%  •  "
                                    f"Education (10%): {r['education_match_score']}%  •  "
                                    f"Certification (5%): {r.get('certification_match_score', 0)}%"
                                )

                                sc1, sc2, sc3 = st.columns(3)
                                with sc1:
                                    st.write("**✅ Matched Skills**")
                                    st.markdown(" ".join(f"`{s}`" for s in r["matched_skills"]) or "—")
                                with sc2:
                                    st.write("**❌ Missing Skills**")
                                    st.markdown(" ".join(f"`{s}`" for s in r["missing_skills"]) or "—")
                                with sc3:
                                    st.write("**➕ Additional Skills**")
                                    st.markdown(" ".join(f"`{s}`" for s in r["additional_skills"]) or "—")

                                st.write("**Recommendations:**")
                                for rec in r["recommendations"]:
                                    st.write(f"- {rec}")

                                st.markdown("")
                                if st.button("➕ Add to Pipeline", key=f"add_pipeline_{r['candidate_id']}", use_container_width=True):
                                    try:
                                        resp = requests.post(
                                            f"{JOBS_API_URL}/applications",
                                            json={"candidate_id": r["candidate_id"], "job_id": selected_job_id, "stage": "Applied"},
                                            timeout=10,
                                        )
                                        resp.raise_for_status()
                                        st.success(f"{r['full_name'] or 'Candidate'} added to pipeline for this job (see **Candidate Pipeline**).")
                                    except Exception as e:
                                        st.error(f"Failed to add to pipeline: {e}")

                        st.markdown("---")
                        df = pd.DataFrame([
                            {
                                "Rank": i + 1,
                                "Candidate": r["full_name"],
                                "Email": r["email"],
                                "Hiring Score (%)": r["hiring_score"],
                                "Skill Match (%)": r["skill_match_pct"],
                                "Skill Gap (%)": r["skill_gap_pct"],
                                "Experience Match (%)": r["experience_match_score"],
                                "Education Match (%)": r["education_match_score"],
                                "Certification Match (%)": r.get("certification_match_score", 0),
                                "Matched Skills": ", ".join(r["matched_skills"]),
                                "Missing Skills": ", ".join(r["missing_skills"]),
                                "Additional Skills": ", ".join(r["additional_skills"]),
                            }
                            for i, r in enumerate(view_results)
                        ])
                        csv_bytes = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "⬇️ Download Skill-Gap Report (CSV)",
                            data=csv_bytes,
                            file_name=f"skill_gap_report_job_{selected_job_id}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )


# ---------------------------------------------------------------------------
# Interview Prep — Milestone 3, Module 1
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Candidate Pipeline — Milestone 3, Module 2 (ATS Integration)
# ---------------------------------------------------------------------------
elif page == "Candidate Pipeline":
    st.title("Candidate Pipeline (ATS)")
    st.caption("Track candidates through recruitment stages, log recruiter notes and feedback, and schedule interviews.")

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        jobs = jobs_resp.json()
    except requests.exceptions.ConnectionError:
        jobs = None
        st.warning(f"Could not reach the Jobs API at {JOBS_API_URL}. Start it with: `uvicorn jobs_api:app --reload --port 8000`")
    except Exception as e:
        jobs = None
        st.error(f"Failed to load job postings: {e}")

    if jobs is not None:
        if not jobs:
            st.info("No job postings yet. Add one on the **Job Postings** page first.")
        else:
            job_labels = {f"{j['job_title']} — {j['company_name']} (#{j['id']})": j["id"] for j in jobs}
            sel_label = st.selectbox("Select a job posting", list(job_labels.keys()), key="pipeline_job")
            selected_job_id = job_labels[sel_label]

            fc1, fc2 = st.columns([2, 1])
            with fc1:
                search_text = st.text_input("Search candidates by name or email", key="pipeline_search")
            with fc2:
                sort_by_score = st.checkbox("Sort by hiring score", key="pipeline_sort_score")

            try:
                apps_resp = requests.get(f"{JOBS_API_URL}/applications", params={"job_id": selected_job_id}, timeout=10)
                apps_resp.raise_for_status()
                applications = apps_resp.json()
            except Exception as e:
                applications = []
                st.error(f"Failed to load pipeline: {e}")

            if search_text:
                s = search_text.strip().lower()
                applications = [
                    a for a in applications
                    if s in (a.get("candidate_name") or "").lower() or s in (a.get("candidate_email") or "").lower()
                ]

            # Sort by hiring score (Module 1: Candidate Dashboard) — pulls the
            # same weighted score used on Candidate Matching, for this job.
            hiring_scores = {}
            if sort_by_score and applications:
                try:
                    m_resp = requests.get(f"{JOBS_API_URL}/jobs/{selected_job_id}/matches", timeout=15)
                    m_resp.raise_for_status()
                    hiring_scores = {r["candidate_id"]: r["hiring_score"] for r in m_resp.json()}
                    applications = sorted(applications, key=lambda a: hiring_scores.get(a["candidate_id"], 0), reverse=True)
                except Exception as e:
                    st.warning(f"Could not load hiring scores for sorting: {e}")

            STAGES = ["Applied", "Screening", "Interview", "Selected", "Rejected"]

            if not applications:
                st.info(
                    "No candidates in this job's pipeline yet. Go to **Candidate Matching**, run matching for this "
                    "job, and click **Add to Pipeline** on a candidate."
                )
            else:
                stage_cols = st.columns(len(STAGES))
                for stage, col in zip(STAGES, stage_cols):
                    with col:
                        st.markdown(f"**{stage}**")
                        stage_apps = [a for a in applications if a["stage"] == stage]
                        st.caption(f"{len(stage_apps)} candidate(s)")
                        for a in stage_apps:
                            score_suffix = f" — {hiring_scores[a['candidate_id']]}%" if a["candidate_id"] in hiring_scores else ""
                            with st.expander((a["candidate_name"] or "Unknown") + score_suffix):
                                st.write(f"**Email:** {a.get('candidate_email') or '—'}")
                                if a.get("candidate_skills"):
                                    st.markdown(" ".join(f"`{s}`" for s in a["candidate_skills"][:6]))

                                # View full candidate profile (Module 1: Candidate Dashboard)
                                with st.popover("👤 View Full Profile"):
                                    full_candidate = next((c for c in get_all_candidates() if c["id"] == a["candidate_id"]), None)
                                    if full_candidate:
                                        render_candidate_card(full_candidate)
                                    else:
                                        st.caption("Profile not found.")

                                # View interview report (Module 1: Candidate Dashboard)
                                reports = db_module.get_interview_reports(job_id=selected_job_id, candidate_id=a["candidate_id"])
                                if reports:
                                    with st.popover(f"🎤 View Interview Report ({reports[0]['overall_score']}%)"):
                                        r = reports[0]
                                        st.metric("Overall Score", f"{r['overall_score']}%")
                                        st.write(f"**Communication Feedback:** {r['communication_feedback']}")
                                        st.write(f"**Strengths:** {r['strengths']}")
                                        st.write(f"**Areas to Improve:** {r['improvements']}")
                                        transcript = json.loads(r.get("qa_transcript") or "[]")
                                        for i, item in enumerate(transcript, start=1):
                                            st.markdown(f"**Q{i}:** {item.get('question')}")
                                            st.caption(f"A: {item.get('response') or '(skipped)'} — {item.get('relevance_score')}%")

                                new_stage = st.selectbox(
                                    "Move to stage",
                                    STAGES,
                                    index=STAGES.index(a["stage"]) if a["stage"] in STAGES else 0,
                                    key=f"stage_select_{a['id']}",
                                )
                                notes = st.text_area("Recruiter notes", value=a.get("recruiter_notes") or "", key=f"notes_{a['id']}")
                                feedback = st.text_area("Feedback", value=a.get("feedback") or "", key=f"feedback_{a['id']}")
                                sched_date = st.date_input(
                                    "Interview date",
                                    value=None,
                                    key=f"sched_date_{a['id']}",
                                )
                                sched_time = st.time_input(
                                    "Interview time",
                                    value=None,
                                    key=f"sched_time_{a['id']}",
                                )

                                if st.button("💾 Save", key=f"save_app_{a['id']}", use_container_width=True):
                                    update_payload = {
                                        "stage": new_stage,
                                        "recruiter_notes": notes,
                                        "feedback": feedback,
                                    }
                                    if sched_date and sched_time:
                                        update_payload["interview_schedule"] = datetime.combine(sched_date, sched_time).isoformat()
                                    try:
                                        resp = requests.put(f"{JOBS_API_URL}/applications/{a['id']}", json=update_payload, timeout=10)
                                        resp.raise_for_status()
                                        st.success("Updated.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to update: {e}")

                                if a.get("interview_schedule"):
                                    st.caption(f"📅 Scheduled: {a['interview_schedule']}")

                                if reports:
                                    st.caption(f"🎤 Latest interview simulation score: {reports[0]['overall_score']}%")

                                if st.button("🗑️ Remove from pipeline", key=f"del_app_{a['id']}", use_container_width=True):
                                    try:
                                        requests.delete(f"{JOBS_API_URL}/applications/{a['id']}", timeout=10)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to remove: {e}")

# ---------------------------------------------------------------------------
# Interview Simulation — Milestone 3, Module 3
# ---------------------------------------------------------------------------
elif page == "Interview Simulation":
    st.title("AI-Powered Interview Simulation")
    st.caption(f"Run a short {MAX_SIMULATION_QUESTIONS}-question mock interview: instant AI evaluation per answer, plus a final performance report.")
    st.info("Responses can be typed, or spoken if the `streamlit-mic-recorder` package is installed.", icon="\u2139\ufe0f")

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        jobs = jobs_resp.json()
    except requests.exceptions.ConnectionError:
        jobs = None
        st.warning(f"Could not reach the Jobs API at {JOBS_API_URL}. Start it with: `uvicorn jobs_api:app --reload --port 8000`")
    except Exception as e:
        jobs = None
        st.error(f"Failed to load job postings: {e}")

    candidates = get_all_candidates() if jobs is not None else []

    if jobs is not None:
        if not jobs or not candidates:
            st.info("You need at least one job posting and one processed candidate to run a simulation.")
        else:
            job_labels = {f"{j['job_title']} \u2014 {j['company_name']} (#{j['id']})": j for j in jobs}
            cand_labels = {f"{c['full_name'] or 'Unknown'} \u2014 {c['email'] or 'no email'} (#{c['id']})": c for c in candidates}

            colA, colB = st.columns(2)
            with colA:
                sim_job_label = st.selectbox("Select a job posting", list(job_labels.keys()), key="sim_job")
            with colB:
                sim_cand_label = st.selectbox("Select a candidate", list(cand_labels.keys()), key="sim_candidate")

            sim_job = job_labels[sim_job_label]
            sim_candidate = cand_labels[sim_cand_label]
            session_key = f"sim_{sim_job['id']}_{sim_candidate['id']}"

            render_interview_simulation(sim_job, sim_candidate, session_key, allow_voice=True)

elif page == "Analytics":
    st.title("Recruitment Analytics")
    candidates = get_all_candidates()

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        an_jobs = jobs_resp.json()
    except Exception:
        an_jobs = []

    try:
        apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=10)
        apps_resp.raise_for_status()
        an_applications = apps_resp.json()
    except Exception:
        an_applications = []

    row1c1, row1c2 = st.columns(2)

    with row1c1:
        st.markdown("#### Top Skills Across Candidates")
        if candidates:
            all_skills = Counter()
            for c in candidates:
                for s in (c["skills"] or []):
                    all_skills[s] += 1
            if all_skills:
                top = all_skills.most_common(10)
                st.bar_chart({s: n for s, n in top})
            else:
                st.caption("No skill data yet.")
        else:
            st.info("Process some resumes to see analytics.")

    with row1c2:
        st.markdown("#### Candidate Distribution by Status")
        if an_applications:
            stage_counts = Counter(a["stage"] for a in an_applications)
            fig = px.pie(names=list(stage_counts.keys()), values=list(stage_counts.values()), hole=0.45)
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No candidates in any pipeline yet.")

    row2c1, row2c2 = st.columns(2)

    with row2c1:
        st.markdown("#### Candidates by Job Role")
        if an_applications:
            role_counts = Counter(f"{a['job_title']}" for a in an_applications)
            st.bar_chart(dict(role_counts.most_common(10)))
        else:
            st.caption("No pipeline data yet.")

    with row2c2:
        st.markdown("#### Selected vs. Rejected")
        stage_counts = Counter(a["stage"] for a in an_applications) if an_applications else Counter()
        sel_rej = {"Selected": stage_counts.get("Selected", 0), "Rejected": stage_counts.get("Rejected", 0)}
        if sum(sel_rej.values()) > 0:
            fig = px.pie(names=list(sel_rej.keys()), values=list(sel_rej.values()), hole=0.45)
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No candidates selected or rejected yet.")

    st.markdown("---")
    st.markdown("#### Hiring Score & Skill Match Distribution (per job)")
    if an_jobs:
        an_job_labels = {f"{j['job_title']} — {j['company_name']} (#{j['id']})": j["id"] for j in an_jobs}
        an_selected_label = st.selectbox("Select a job posting", list(an_job_labels.keys()), key="analytics_job")
        an_job_id = an_job_labels[an_selected_label]

        try:
            m_resp = requests.get(f"{JOBS_API_URL}/jobs/{an_job_id}/matches", timeout=15)
            m_resp.raise_for_status()
            match_results = m_resp.json()
        except Exception as e:
            match_results = []
            st.error(f"Failed to load matches: {e}")

        if match_results:
            distc1, distc2 = st.columns(2)
            with distc1:
                st.caption("Hiring Score Distribution")
                fig = px.histogram(x=[r["hiring_score"] for r in match_results], nbins=10, labels={"x": "Hiring Score (%)"})
                fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Candidates")
                st.plotly_chart(fig, use_container_width=True)
            with distc2:
                st.caption("Skill Match Distribution")
                fig = px.histogram(x=[r["skill_match_pct"] for r in match_results], nbins=10, labels={"x": "Skill Match (%)"})
                fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Candidates")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No candidates matched against this job yet.")
    else:
        st.caption("No job postings yet.")

    st.markdown("---")
    st.markdown("#### Interview Performance")
    all_reports = db_module.get_interview_reports()
    if all_reports:
        fig = px.histogram(x=[float(r["overall_score"]) for r in all_reports], nbins=10, labels={"x": "Interview Score (%)"})
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Interviews")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Based on {len(all_reports)} completed interview simulation(s) across all jobs.")
    else:
        st.caption("No interview simulations completed yet.")

elif page == "Settings":
    st.title("Settings")
    st.markdown("#### Environment")
    st.code(
        f"""DB_HOST      = {os.getenv('DB_HOST', 'localhost')}
DB_NAME      = {os.getenv('DB_NAME', 'recruitment_copilot')}
GEMINI_MODEL = {os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')}
GEMINI_API_KEY set = {bool(os.getenv('GEMINI_API_KEY'))}
""",
        language="text",
    )
    st.caption(f"Server time: {datetime.now().isoformat(timespec='seconds')}")

# ---------------------------------------------------------------------------
# Milestone 4 — Candidate (User) Side
# ---------------------------------------------------------------------------
elif page == "My Dashboard":
    st.title("My Dashboard")
    st.caption(f"Welcome back, {current_user['name']}.")

    if not current_user.get("candidate_id"):
        st.info("Upload your resume on **My Profile** to unlock your dashboard, applications, and interviews.")
    else:
        my_candidate_id = current_user["candidate_id"]
        try:
            apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=10)
            apps_resp.raise_for_status()
            my_applications = [a for a in apps_resp.json() if a["candidate_id"] == my_candidate_id]
        except Exception as e:
            my_applications = []
            st.error(f"Failed to load your applications: {e}")

        my_reports_all = db_module.get_interview_reports(candidate_id=my_candidate_id)
        finished_job_ids = {r["job_id"] for r in my_reports_all}

        applied_count = len(my_applications)
        screening_count = sum(1 for a in my_applications if a["stage"] == "Screening")
        shortlisted_count = sum(1 for a in my_applications if a["stage"] in ("Interview", "Selected"))
        scheduled_count = sum(1 for a in my_applications if a.get("interview_schedule"))
        finished_count = sum(1 for a in my_applications if a["job_id"] in finished_job_ids)
        rejected_count = sum(1 for a in my_applications if a["stage"] == "Rejected")

        st.markdown("### Overview")
        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.metric("Applied Jobs", applied_count)
        r1c2.metric("Screening", screening_count)
        r1c3.metric("Shortlisted", shortlisted_count)

        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.metric("Interview Scheduled", scheduled_count)
        r2c2.metric("Interview Finished", finished_count)
        r2c3.metric("Rejected", rejected_count)

        if my_applications:
            st.markdown("#### Application Status Breakdown")
            chart_labels = ["Applied", "Screening", "Shortlisted", "Interview Scheduled", "Interview Finished", "Rejected"]
            chart_values = [applied_count, screening_count, shortlisted_count, scheduled_count, finished_count, rejected_count]
            fig = px.bar(x=chart_labels, y=chart_values, labels={"x": "", "y": "Count"})
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Pipeline Stage Distribution")
            stage_counts = Counter(a["stage"] for a in my_applications)
            fig2 = px.pie(names=list(stage_counts.keys()), values=list(stage_counts.values()), hole=0.45)
            fig2.update_traces(textinfo="label+percent")
            fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("### My Applications")
        if not my_applications:
            st.info("You haven't applied to any jobs yet. Browse **Job Openings** to get started.")
        else:
            for a in my_applications:
                with st.expander(f"{a['job_title']} — {a['company_name']}  ·  Stage: {a['stage']}"):
                    st.write(f"**Current Stage:** {a['stage']}")
                    if a.get("interview_schedule"):
                        st.write(f"**Interview Scheduled:** {a['interview_schedule']}")
                    if a.get("feedback"):
                        st.write(f"**Recruiter Feedback:** {a['feedback']}")

                    my_reports = db_module.get_interview_reports(job_id=a["job_id"], candidate_id=my_candidate_id)
                    if my_reports:
                        r = my_reports[0]
                        st.markdown("**Your latest interview simulation:**")
                        st.metric("Score", f"{r['overall_score']}%")
                        st.write(f"Strengths: {r['strengths']}")
                        st.write(f"Areas to improve: {r['improvements']}")

# ---------------------------------------------------------------------------
elif page == "My Profile":
    st.title("My Profile")

    if current_user.get("candidate_id"):
        my_candidate = next((c for c in get_all_candidates() if c["id"] == current_user["candidate_id"]), None)
        if my_candidate:
            render_candidate_card(my_candidate)
            st.markdown("---")
        st.caption("Upload a new resume below to replace your profile.")
    else:
        st.info("Upload your resume to create your profile. This lets you apply to jobs and take interviews.")

    uploaded_file = st.file_uploader("Upload your resume", type=["pdf", "docx"], key="candidate_resume_upload")
    if uploaded_file is not None and st.button("⚙️ Process My Resume", type="primary"):
        with st.spinner("Extracting and structuring your resume..."):
            try:
                file_bytes = uploaded_file.getvalue()
                raw_text = extract_text(uploaded_file.name, file_bytes)
                data = extract_candidate_data(raw_text)
                saved = insert_candidate(data, uploaded_file.name, raw_text)
                db_module.link_candidate_to_user(current_user["id"], saved["id"])
                current_user["candidate_id"] = saved["id"]
                st.session_state.user = current_user
                st.success("Profile created from your resume.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to process resume: {e}")

# ---------------------------------------------------------------------------
elif page == "Job Openings":
    st.title("Job Openings")
    st.caption("Browse open roles and apply.")

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        open_jobs = [j for j in jobs_resp.json() if (j.get("status") or "Open") == "Open"]
    except Exception as e:
        open_jobs = []
        st.error(f"Failed to load job postings: {e}")

    if not open_jobs:
        st.info("No open roles right now — check back later.")
    else:
        for job in open_jobs:
            with st.expander(f"{job['job_title']} — {job['company_name']}"):
                render_job_card(job)
                if not current_user.get("candidate_id"):
                    st.caption("Upload your resume on **My Profile** before applying.")
                elif st.button("📩 Apply", key=f"apply_{job['id']}"):
                    try:
                        resp = requests.post(
                            f"{JOBS_API_URL}/applications",
                            json={"candidate_id": current_user["candidate_id"], "job_id": job["id"], "stage": "Applied"},
                            timeout=10,
                        )
                        resp.raise_for_status()
                        st.success("Application submitted — track it on My Dashboard.")
                    except Exception as e:
                        st.error(f"Failed to apply: {e}")

# ---------------------------------------------------------------------------
elif page == "Interview Prep":
    st.title("Interview Prep")
    st.caption("Generate a tailored practice question set for a job you've applied to — technical, behavioural, and skill-specific follow-ups.")

    if not current_user.get("candidate_id"):
        st.info("Upload your resume on **My Profile** first.")
    else:
        my_candidate_id = current_user["candidate_id"]
        my_candidate = next((c for c in get_all_candidates() if c["id"] == my_candidate_id), None)
        try:
            apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=10)
            apps_resp.raise_for_status()
            my_applications = [a for a in apps_resp.json() if a["candidate_id"] == my_candidate_id]
        except Exception as e:
            my_applications = []
            st.error(f"Failed to load your applications: {e}")

        if not my_applications:
            st.info("Apply to a job on **Job Openings** first, then come back here to prepare for it.")
        elif not my_candidate:
            st.error("Could not load your profile.")
        else:
            app_labels = {f"{a['job_title']} — {a['company_name']}": a["job_id"] for a in my_applications}
            sel_label = st.selectbox("Select a job you've applied to", list(app_labels.keys()), key="prep_job_candidate")
            sel_job_id = app_labels[sel_label]

            try:
                job_resp = requests.get(f"{JOBS_API_URL}/jobs/{sel_job_id}", timeout=10)
                job_resp.raise_for_status()
                sel_job = job_resp.json()
            except Exception as e:
                sel_job = None
                st.error(f"Failed to load job: {e}")

            if sel_job:
                existing = db_module.get_interview_questions(my_candidate_id, sel_job["id"])
                btn_label = "🔄 Regenerate Questions" if existing else "✨ Generate Practice Questions"

                if st.button(btn_label, type="primary"):
                    with st.spinner("Analyzing the job description and your profile with Gemini..."):
                        try:
                            questions = interview_ai.generate_interview_questions(sel_job, my_candidate)
                            db_module.upsert_interview_questions(
                                my_candidate_id, sel_job["id"],
                                json.dumps(questions.get("technical_questions", [])),
                                json.dumps(questions.get("behavioral_questions", [])),
                                json.dumps(questions.get("follow_up_questions", [])),
                            )
                            st.session_state.candidate_prep_questions = questions
                            st.success("Practice questions generated.")
                        except Exception as e:
                            st.error(f"Failed to generate interview questions: {e}")

                questions_to_show = st.session_state.get("candidate_prep_questions")
                if questions_to_show is None and existing:
                    questions_to_show = {
                        "technical_questions": json.loads(existing["technical_questions"] or "[]"),
                        "behavioral_questions": json.loads(existing["behavioral_questions"] or "[]"),
                        "follow_up_questions": json.loads(existing["follow_up_questions"] or "[]"),
                    }

                if questions_to_show:
                    st.markdown(f"### Practice Questions — {sel_job['job_title']} at {sel_job['company_name']}")
                    render_interview_questions(questions_to_show)

# ---------------------------------------------------------------------------
elif page == "My Interview":
    st.title("My Interview")
    st.caption(f"Practice a short {MAX_SIMULATION_QUESTIONS}-question AI mock interview. Answer by voice or text.")

    if not current_user.get("candidate_id"):
        st.info("Upload your resume on **My Profile** first.")
    else:
        my_candidate_id = current_user["candidate_id"]
        my_candidate = next((c for c in get_all_candidates() if c["id"] == my_candidate_id), None)
        try:
            apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=10)
            apps_resp.raise_for_status()
            my_applications = [a for a in apps_resp.json() if a["candidate_id"] == my_candidate_id]
        except Exception as e:
            my_applications = []
            st.error(f"Failed to load your applications: {e}")

        # Interview simulation only unlocks once a recruiter moves the
        # candidate's application into the Interview stage (or beyond).
        eligible_applications = [a for a in my_applications if a["stage"] in ("Interview", "Selected")]

        if not eligible_applications:
            st.info(
                "Interview simulation isn't available yet for any of your applications. "
                "It unlocks once a recruiter moves you to the **Interview** stage — check **My Dashboard** "
                "to see where each application currently stands."
            )
        elif not my_candidate:
            st.error("Could not load your profile.")
        else:
            app_labels = {f"{a['job_title']} — {a['company_name']}": a["job_id"] for a in eligible_applications}
            sel_label = st.selectbox("Select a job", list(app_labels.keys()), key="candidate_interview_job")
            sel_job_id = app_labels[sel_label]

            try:
                job_resp = requests.get(f"{JOBS_API_URL}/jobs/{sel_job_id}", timeout=10)
                job_resp.raise_for_status()
                sel_job = job_resp.json()
            except Exception as e:
                sel_job = None
                st.error(f"Failed to load job: {e}")

            if sel_job:
                session_key = f"sim_{sel_job['id']}_{my_candidate_id}"
                render_interview_simulation(sel_job, my_candidate, session_key, allow_voice=True)

# ---------------------------------------------------------------------------
# Milestone 4 — Admin Dashboard
# ---------------------------------------------------------------------------
elif page == "Admin Dashboard":
    st.title("Admin Dashboard")
    st.caption("Platform-wide oversight — manage every candidate and recruiter account, job posting, and interview from one place.")

    all_users = db_module.list_users()
    candidate_users = [u for u in all_users if u["role"] == "candidate"]
    recruiter_users = [u for u in all_users if u["role"] == "recruiter"]
    all_candidates = get_all_candidates()

    try:
        jobs_resp = requests.get(f"{JOBS_API_URL}/jobs", timeout=10)
        jobs_resp.raise_for_status()
        admin_jobs = jobs_resp.json()
    except Exception:
        admin_jobs = []

    try:
        apps_resp = requests.get(f"{JOBS_API_URL}/applications", timeout=10)
        apps_resp.raise_for_status()
        admin_applications = apps_resp.json()
    except Exception:
        admin_applications = []

    all_reports = db_module.get_interview_reports()

    # -----------------------------------------------------------------
    # Top-line metrics
    # -----------------------------------------------------------------
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Total Candidates", len(all_candidates))
    a2.metric("Total Jobs", len(admin_jobs))
    a3.metric("Recruiters", len(recruiter_users))
    a4.metric("Interviews Scheduled", sum(1 for a in admin_applications if a.get("interview_schedule")))

    # -----------------------------------------------------------------
    # Candidate Pipeline (funnel)
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Candidate Pipeline")
    stage_counts = Counter(a["stage"] for a in admin_applications) if admin_applications else Counter()
    if admin_applications:
        pipeline_order = ["Applied", "Screening", "Interview", "Selected", "Rejected"]
        funnel_counts = [stage_counts.get(s, 0) for s in pipeline_order]
        fig_funnel = px.funnel(x=funnel_counts, y=pipeline_order)
        fig_funnel.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_funnel, use_container_width=True)
    else:
        st.caption("No candidates in any pipeline yet.")

    # -----------------------------------------------------------------
    # Job & Candidate Analytics
    # -----------------------------------------------------------------
    st.markdown("### Job & Candidate Analytics")
    j1, j2 = st.columns(2)

    with j1:
        st.caption("Jobs by Status")
        if admin_jobs:
            job_status_counts = Counter((j.get("status") or "Open") for j in admin_jobs)
            fig = px.pie(names=list(job_status_counts.keys()), values=list(job_status_counts.values()), hole=0.45)
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No job postings yet.")

    with j2:
        st.caption("Candidates by Status")
        if admin_applications:
            fig = px.pie(names=list(stage_counts.keys()), values=list(stage_counts.values()), hole=0.45)
            fig.update_traces(textinfo="label+percent")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No candidates in any pipeline yet.")

    # -----------------------------------------------------------------
    # Interview Analytics
    # -----------------------------------------------------------------
    st.markdown("### Interview Analytics")

    scheduled_apps = [a for a in admin_applications if a.get("interview_schedule")]
    completed_pairs = {(r["candidate_id"], r["job_id"]) for r in all_reports}
    completed_count = sum(1 for a in scheduled_apps if (a["candidate_id"], a["job_id"]) in completed_pairs)
    pending_count = len(scheduled_apps) - completed_count
    avg_score = round(sum(float(r["overall_score"]) for r in all_reports) / len(all_reports), 1) if all_reports else None

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Total Interviews", len(scheduled_apps))
    i2.metric("Completed", completed_count)
    i3.metric("Pending", pending_count)
    i4.metric("Average Score", f"{avg_score}%" if avg_score is not None else "—")

    if len(scheduled_apps) > 0:
        fig = px.pie(
            names=["Completed", "Pending"],
            values=[completed_count, pending_count],
            hole=0.5,
            color_discrete_sequence=["#2E8B57", "#D9A441"],
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    if all_reports:
        st.caption("Interview Score Distribution")
        fig = px.histogram(x=[float(r["overall_score"]) for r in all_reports], nbins=10, labels={"x": "Interview Score (%)"})
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), yaxis_title="Interviews")
        st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------------------
    # User Management — manage both candidate-side and recruiter-side accounts
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("### User Management")
    st.caption(f"{len(candidate_users)} candidate account(s) · {len(recruiter_users)} recruiter account(s)")
    search = st.text_input("Search users by name or email", key="admin_user_search")

    filtered_users = all_users
    if search:
        s = search.strip().lower()
        filtered_users = [u for u in all_users if s in u["name"].lower() or s in u["email"].lower()]

    for u in filtered_users:
        with st.expander(f"{u['name']} — {u['email']}  ·  {u['role']}" + ("" if u["is_active"] else "  (deactivated)")):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_role = st.selectbox(
                    "Role", ["candidate", "recruiter", "admin"],
                    index=["candidate", "recruiter", "admin"].index(u["role"]),
                    key=f"role_{u['id']}",
                )
            with c2:
                new_active = st.checkbox("Active", value=u["is_active"], key=f"active_{u['id']}")
            with c3:
                st.write("")
                st.write("")
                if st.button("💾 Save", key=f"save_user_{u['id']}", use_container_width=True):
                    try:
                        if new_role != u["role"]:
                            db_module.update_user_role(u["id"], new_role)
                        if new_active != u["is_active"]:
                            db_module.set_user_active(u["id"], new_active)
                        st.success("Updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update user: {e}")

    # -----------------------------------------------------------------
    # Job Postings — admin oversight (recruiter-side content)
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("### All Job Postings")
    if not admin_jobs:
        st.caption("No job postings yet.")
    else:
        for j in admin_jobs:
            jc1, jc2, jc3 = st.columns([3, 1, 1])
            jc1.write(f"**{j['job_title']}** — {j['company_name']}")
            jc2.write(j.get("status") or "Open")
            with jc3:
                if st.button("🗑️ Delete", key=f"admin_del_job_{j['id']}", use_container_width=True):
                    try:
                        requests.delete(f"{JOBS_API_URL}/jobs/{j['id']}", timeout=10)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete job: {e}")

    # -----------------------------------------------------------------
    # Candidate Profiles — admin oversight (candidate-side content)
    # -----------------------------------------------------------------
    st.markdown("### All Candidate Profiles")
    if not all_candidates:
        st.caption("No candidate profiles yet.")
    else:
        for c in all_candidates:
            cc1, cc2, cc3 = st.columns([3, 2, 1])
            cc1.write(f"**{c['full_name'] or 'Unknown'}**")
            cc2.write(c.get("email") or "—")
            with cc3:
                if st.button("🗑️ Delete", key=f"admin_del_cand_{c['id']}", use_container_width=True):
                    try:
                        delete_candidate(c["id"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete candidate: {e}")
