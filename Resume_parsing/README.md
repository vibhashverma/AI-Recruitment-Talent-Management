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
├── app.py               # Streamlit UI (Dashboard, Resume Upload, Candidates, Analytics)
├── db.py                # PostgreSQL connection + queries
├── resume_parser.py     # PDF/DOCX -> raw text
├── gemini_extractor.py  # raw text -> structured JSON via Gemini
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
```

## 4. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Run

```bash
streamlit run app.py
```

The app loads `.env` automatically via `python-dotenv`. Open the URL Streamlit
prints (usually http://localhost:8501).

## How it works

1. **Upload** — user drops a PDF or DOCX resume on the *Resume Upload* page.
2. **Parse** — `resume_parser.py` extracts raw text (PyMuPDF for PDF, python-docx for DOCX).
3. **Extract** — `gemini_extractor.py` sends the raw text to Gemini with a strict JSON
   schema prompt (full name, email, phone, location, education, experience, skills,
   certifications, projects).
4. **Store** — `db.py` inserts the structured profile into the PostgreSQL `candidates` table.
5. **Display** — the parsed profile, plus a running table of recently processed
   candidates and simple analytics, render in the Streamlit UI.

## Notes / next steps

- Job Postings, deeper Analytics, and Settings are stubbed for future milestones.
- For scanned/image-only PDFs, add OCR (e.g. `pytesseract`) — plain text extraction
  will fail on those since there's no text layer.
- Consider rate-limiting/retry handling around the Gemini call for production use.
