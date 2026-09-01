# Recruitment Copilot — Milestone 1

Resume parsing & candidate profiling system.

**Stack**
- Frontend: Streamlit
- Database: PostgreSQL
- LLM: Google Gemini API (structured extraction)
- Parsing: PyMuPDF (PDF), python-docx (DOCX)

## Project structure

```
recruitment_copilot/
├── app.py               # Streamlit UI — role-gated: recruiter, candidate, and admin pages
├── auth.py              # Login/signup, password hashing, admin bootstrap, role gate
├── db.py                # PostgreSQL connection + queries (candidates, job_postings, applications, interview_questions, interview_reports, users)
├── resume_parser.py     # PDF/DOCX -> raw text
├── gemini_extractor.py  # raw text -> structured JSON via Gemini
├── jobs_api.py          # FastAPI service: job postings, matching, and ATS pipeline endpoints
├── matching.py          # Candidate-job matching engine + hiring score
├── interview_ai.py      # Gemini-based interview question generation, evaluation, reports, and voice transcription
├── tests/
│   └── test_matching.py # Standalone pytest suite for the matching engine
├── schema.sql           # DB schema (also auto-created on first run)
├── requirements.txt
├── .env.example
└── README.md
```

## 1. Set up PostgreSQL

```bash
createdb recruitment_copilot
# schema.sql is optional — app.py calls init_db() automatically on startup
psql -d recruitment_copilot -f schema.sql
```

## 2. Get a Gemini API key

Create a key at https://aistudio.google.com/apikey

## 3. Configure environment

```bash
cp .env.example .env
# edit .env: set DB_* credentials and GEMINI_API_KEY
# also set ADMIN_EMAIL and ADMIN_PASSWORD — an admin account is auto-created
# from these on first run (see "Authentication & Roles" below)
```

## 4. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Run

Start the Jobs API (FastAPI) first, then the Streamlit app, in two terminals:

```bash
# Terminal 1 — Job Postings API
uvicorn jobs_api:app --reload --port 8000

# Terminal 2 — Streamlit app
streamlit run app.py
```

Both load `.env` automatically via `python-dotenv`. Open the URL Streamlit
prints (usually http://localhost:8501). The **Job Postings** page in the
sidebar talks to the FastAPI service at `JOBS_API_URL` (defaults to
`http://localhost:8000`) — set that env var if you run the API elsewhere.

You can also browse the interactive API docs at http://localhost:8000/docs.

## How it works

1. **Upload** — user drops a PDF or DOCX resume on the *Resume Upload* page.
2. **Parse** — `resume_parser.py` extracts raw text (PyMuPDF for PDF, python-docx for DOCX).
3. **Extract** — `gemini_extractor.py` sends the raw text to Gemini with a strict JSON
   schema prompt (full name, email, phone, location, education, experience, skills,
   certifications, projects).
4. **Store** — `db.py` inserts the structured profile into the PostgreSQL `candidates` table.
5. **Display** — the parsed profile, plus a running table of recently processed
   candidates and simple analytics, render in the Streamlit UI.

## Job Postings

The **Job Postings** page lets recruiters record open roles: Job Title,
Company Name, Location, Experience, Skills, Education, and Certification.
Submissions go through the `jobs_api.py` FastAPI service, which validates
the payload (Pydantic) and writes it to the `job_postings` table in
PostgreSQL. The same page lists existing postings and lets you **edit**
(via `PUT /jobs/{id}`) or **delete** (`DELETE /jobs/{id}`) them.

## Candidate Matching & Hiring Score (Milestone 2)

The **Candidate Matching** page lets a recruiter pick a job posting and score
every candidate in the database against it, via `matching.py` and the
`GET /jobs/{id}/matches` endpoint on the FastAPI service:

- **Skill comparison** — Matched / Missing / Additional skills (case-insensitive).
- **Experience match** — parses free-text experience (e.g. "3-5 years") on
  both sides and scores how close the candidate is to the requirement.
- **Education match** — keyword-overlap heuristic (neutral 100% if the job
  doesn't specify education).
- **Certification match** — same keyword-overlap heuristic against the job's
  certification requirement.
- **Hiring Score** — a fixed weighted blend:
  **Skill 60% + Experience 25% + Education 10% + Certification 5%**,
  ranked descending by default.
- **Sort & filter** — a "Sort by" control (Top Ranker / Top 10 / Ascending /
  Descending) plus a free-text filter box (matches candidate name or any
  matched/missing/additional skill).
- **Skill-gap report** — matched/missing/additional skills, skill-gap %,
  plain-language recommendations per candidate, a bar chart of hiring
  scores, and a downloadable CSV report.

This is a rules-based heuristic, not an LLM judgment call — it's fast,
deterministic, and free to run, but the education/certification scoring is
intentionally simple keyword overlap. Swapping in an LLM-based comparison
for nuanced cases would be a natural next iteration.

## Dashboard

The Dashboard now shows two pie charts for a quick recruiter-facing overview:
**Job Postings by Status** (Open / On Hold / Closed) and **Top Skills Across
Candidates** (top 6 skills, with the rest grouped as "Others"), built with
Plotly. These sit above the existing metrics and recent-candidates table.

## AI Interview & Candidate Management (Milestone 3)

Three new pages extend the platform from "who fits" into active interview
and pipeline management, backed by a new `interview_ai.py` module (Gemini)
and new `applications` / `interview_questions` / `interview_reports` tables.

### Interview Prep (Module 1 — Role-Specific Question Generation)

Pick a job and a candidate, and Gemini generates a tailored question set
based on the job's actual requirements and the candidate's actual resume:
- **Technical questions**, categorized Beginner / Intermediate / Advanced.
- **Behavioural questions** (situational, teamwork, ownership, etc.).
- **Follow-up questions**, each tied to a specific skill on the candidate's
  resume, for probing deeper in the interview.

Questions are cached per candidate/job pair (`interview_questions` table)
so they don't need regenerating every visit; a "Regenerate" button is
available if the job or candidate profile changes.

### Candidate Pipeline (Module 2 — ATS Integration)

A lightweight ATS: pick a job and see candidates laid out in columns by
recruitment stage (**Applied → Screening → Interview → Selected →
Rejected**). Each candidate card supports:
- Moving to a different stage.
- Recruiter notes and feedback (free text).
- Interview date/time scheduling.
- A quick link back to their latest interview simulation score, if one exists.
- Search/filter by candidate name or email.

Candidates enter the pipeline via an **"➕ Add to Pipeline"** button on the
**Candidate Matching** results, so shortlisting flows directly into ATS
tracking. This is served by new `POST/GET/PUT/DELETE /applications`
endpoints on the FastAPI service.

### Interview Simulation (Module 3 — AI-Powered Mock Interviews)

Pick a job and candidate, and run a full mock interview:
- Questions are presented one at a time (reusing Interview Prep's saved
  set, or generating one on the fly).
- Each written response is evaluated live by Gemini for relevance,
  communication quality, strengths, and improvement areas.
- After all questions, a **performance report** is generated: an overall
  score, communication feedback, strengths, and improvement suggestions,
  saved to `interview_reports` and surfaced back on the Candidate Pipeline
  card for that candidate.

**Scope note:** simulation currently accepts **written responses only**.
Voice input/output would need additional speech-to-text and text-to-speech
infrastructure (e.g. a browser microphone capture + a transcription API)
that wasn't part of this milestone's environment — flagged here as a
natural next step rather than silently left out.

## Authentication & Roles (Milestone 4)

Three roles now share the same app, gated by a login screen (`auth.py`) that
appears before anything else loads:

- **Candidate** — signs up, uploads their resume on **My Profile** (which
  creates/links their `candidates` row), browses **Job Openings** and
  applies with one click, tracks status on **My Dashboard**, and can take a
  short self-service mock interview on **My Interview**.
- **Recruiter** — signs up and gets the full Milestones 1–3 toolset:
  Resume Upload, Candidates, Job Postings, Candidate Matching, Interview
  Prep, Candidate Pipeline, Interview Simulation, and Analytics.
- **Admin** — not signed up through the UI. Instead, set `ADMIN_EMAIL` and
  `ADMIN_PASSWORD` in `.env`; the account is created automatically the
  first time the app starts (`auth.ensure_admin_bootstrapped()`). Admins
  get an **Admin Dashboard** plus the full recruiter toolset.

Passwords are hashed with bcrypt before they're ever written to the
`users` table — the app never stores or compares plaintext passwords.

**How the two sides interact:** a candidate applying via **Job Openings**
calls the same `POST /applications` endpoint as a recruiter's "Add to
Pipeline" button — both write to the same `applications` row. A recruiter
moving a candidate's stage or leaving feedback on **Candidate Pipeline**
is immediately visible to that candidate on **My Dashboard**, and a
candidate's self-service interview report (from **My Interview**) shows up
on the recruiter's **Candidate Pipeline** card for that job.

## Recruiter Dashboard (Milestone 4, Module 1)

The **Dashboard** page now leads with the metrics called for on this
milestone: Total Candidates, Total Job Openings, Candidates Shortlisted,
Interviews Scheduled, Selected Candidates, Rejected Candidates, and
Average Hiring Score, plus a **Candidate Pipeline** funnel chart (Plotly)
showing volume at each stage. The existing Job-Postings-by-Status and
Top-Skills pie charts remain below as a secondary overview.

The **Candidate Pipeline** page (the "Candidate Dashboard" from the spec)
adds: a **Sort by hiring score** toggle (pulls live scores from the
matching engine for the selected job), a **View Full Profile** popover per
candidate, and a **View Interview Report** popover showing their latest
simulation score, feedback, and full transcript — alongside the existing
search, stage management, notes/feedback, and scheduling.

**Recruitment Analytics** (the **Analytics** page) now covers every chart
called for: Candidate Distribution by Status, Candidates by Job Role,
Selected vs. Rejected, Hiring Score Distribution and Skill Match
Distribution (per selected job, pulled from the matching engine), and
Interview Performance (distribution of all completed simulation scores).

## Voice-Based Screening (Milestone 4, Module 2)

Both **Interview Simulation** (recruiter-run) and **My Interview**
(candidate self-service) now support answering by voice. Recording uses
the `streamlit-mic-recorder` widget; the captured audio is sent straight
to Gemini (`interview_ai.transcribe_audio`) for transcription, and the
result pre-fills the text response box — so voice is an alternative input
method, not a separate code path from the existing evaluation flow. If a
microphone or the package isn't available, typing still works exactly as
before.

## Shorter Interview Simulation

Mock interviews are capped at **3 questions** (`MAX_SIMULATION_QUESTIONS`
in `app.py`), pulled from the technical and behavioural sets generated on
**Interview Prep**. This keeps both the recruiter-run and candidate
self-service simulations quick to complete, and both pages share one
implementation (`render_interview_simulation()`) so the question count,
voice support, and report generation stay consistent between them.

## Testing (Milestone 4, Module 3)

`tests/test_matching.py` is a standalone pytest suite (no PostgreSQL, no
Gemini, no network) covering the matching engine's pure functions:
experience parsing, skill matching, the weighted hiring-score formula, and
ranking order. Run it with:

```bash
pytest tests/test_matching.py -v
```

This covers the piece of the system that's cheapest and safest to test in
isolation. The rest of the stack (resume parsing, Gemini extraction, the
FastAPI service, the Streamlit UI, and the full apply → shortlist →
interview → hire workflow) was validated manually end-to-end rather than
with automated integration tests, since that would need a live
PostgreSQL instance and Gemini API access to run in CI.

## Optimization (Milestone 4, Module 4)

The Dashboard's "Average Hiring Score" metric is the one place that could
fan out to an unbounded number of API calls (one `/jobs/{id}/matches` call
per open job). It's capped to the first 5 open jobs per render, so the
Dashboard stays fast even as job postings grow — called out explicitly in
`app.py` rather than left as a silent limitation.

## Deployment

For a local/demo deployment: run PostgreSQL, `uvicorn jobs_api:app` (the
FastAPI service), and `streamlit run app.py` as three long-running
processes (see the Run section above). For anything beyond a local demo,
put a process manager (e.g. `systemd`, Docker Compose, or a Procfile) in
front of the two Python processes and point `JOBS_API_URL` at wherever the
FastAPI service ends up running.

## Notes / next steps

- Deeper Analytics and Settings are stubbed for future milestones.
- For scanned/image-only PDFs, add OCR (e.g. `pytesseract`) — plain text extraction
  will fail on those since there's no text layer.
- Consider rate-limiting/retry handling around the Gemini call for production use.
