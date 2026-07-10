"""
gemini_extractor.py
Uses the Gemini API to convert unstructured resume text into a structured
candidate profile (JSON).
"""

import json
import os
import re

import google.generativeai as genai

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file or environment."
            )
        genai.configure(api_key=api_key)
        _configured = True


EXTRACTION_PROMPT = """You are a resume parsing engine. Extract structured candidate
data from the resume text below. Return ONLY valid JSON — no markdown code fences,
no commentary — matching exactly this schema:

{{
  "full_name": string or null,
  "email": string or null,
  "phone": string or null,
  "location": string or null,
  "education": string or null,
  "experience_years": string or null,
  "experience_details": string or null,
  "skills": [string, ...],
  "certifications": string or null,
  "projects": string or null
}}

Rules:
- "experience_years" should be a short value like "5 years".
- "skills" must be a flat list of individual skill names, most relevant first (max 15).
- "education" should summarize degree(s) and institution(s) in one line.
- "experience_details" should briefly summarize roles/companies (2-4 sentences max).
- "projects" should briefly summarize notable projects (2-4 sentences max).
- If a field cannot be found, use null (or [] for skills). Never invent information.

Resume text:
\"\"\"
{resume_text}
\"\"\"
"""


def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return raw


def extract_candidate_data(resume_text: str) -> dict:
    """Call Gemini and return a dict matching the candidate schema."""
    _ensure_configured()

    model = genai.GenerativeModel(MODEL_NAME)
    prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:15000])

    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )

    cleaned = _strip_code_fences(response.text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse Gemini response as JSON:\n{response.text}")
        data = json.loads(match.group(0))

    data.setdefault("skills", [])
    if not isinstance(data["skills"], list):
        data["skills"] = [str(data["skills"])]

    for field in (
        "full_name", "email", "phone", "location", "education",
        "experience_years", "experience_details", "certifications", "projects",
    ):
        data.setdefault(field, None)

    return data
