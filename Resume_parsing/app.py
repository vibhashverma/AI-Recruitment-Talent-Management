"""
app.py
Recruitment Copilot — Milestone 1: Resume Parsing & Candidate Profiling.

Run with:  streamlit run app.py
"""

import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db import (
    delete_candidate,
    get_all_candidates,
    get_dashboard_stats,
    init_db,
    insert_candidate,
)
from gemini_extractor import extract_candidate_data
from resume_parser import extract_text



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

if "last_extracted" not in st.session_state:
    st.session_state.last_extracted = None
if "last_filename" not in st.session_state:
    st.session_state.last_filename = None

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("##  Recruitment Copilot")
    page = st.radio(
        "Navigate",
        [
            "Dashboard",
            "Resume Upload",
            "Candidates",
            # "Job Postings",   # hidden for now
            # "Analytics",      # hidden for now
            # "Settings",       # hidden for now
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def metric_card(label, value, sublabel=None):
    st.metric(label, value)
    if sublabel:
        st.caption(sublabel)


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


# ---------------------------------------------------------------------------
# DB connection guard
# ---------------------------------------------------------------------------
if not st.session_state.db_ready:
    st.error(
        "Could not connect to PostgreSQL. Check your DB settings in `.env`.\n\n"
        f"Details: {st.session_state.get('db_error')}"
    )
    st.stop()

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
    st.info("Job posting management is planned for a future milestone.")

elif page == "Analytics":
    st.title("Analytics")
    candidates = get_all_candidates()
    if candidates:
        from collections import Counter

        all_skills = Counter()
        for c in candidates:
            for s in (c["skills"] or []):
                all_skills[s] += 1

        st.markdown("#### Top Skills Across Candidates")
        if all_skills:
            top = all_skills.most_common(10)
            st.bar_chart({s: n for s, n in top})
        else:
            st.caption("No skill data yet.")
    else:
        st.info("Process some resumes to see analytics.")

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
