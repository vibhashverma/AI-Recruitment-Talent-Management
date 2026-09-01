"""
interview_ai.py
Milestone 3 — AI Interview & Candidate Assessment.

Uses the Gemini API to:
1. Generate role-specific technical + behavioural interview questions from a
   job posting and a candidate profile (Module 1).
2. Evaluate a candidate's simulated interview response (Module 3).
3. Summarize a full mock-interview transcript into a performance report (Module 3).
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


def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return raw


def _call_gemini_json(prompt: str) -> dict:
    _ensure_configured()
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    cleaned = _strip_code_fences(response.text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse Gemini response as JSON:\n{response.text}")
        return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Module 1 — Role-Specific Interview Question Generation
# ---------------------------------------------------------------------------

QUESTION_GEN_PROMPT = """You are an expert technical interviewer. Based on the job posting and candidate
profile below, generate a tailored interview question set. Return ONLY valid JSON — no markdown
fences, no commentary — matching exactly this schema:

{{
  "technical_questions": [
    {{"question": string, "difficulty": "Beginner" | "Intermediate" | "Advanced"}}
  ],
  "behavioral_questions": [
    {{"question": string, "difficulty": "Beginner" | "Intermediate" | "Advanced"}}
  ],
  "follow_up_questions": [
    {{"question": string, "based_on_skill": string}}
  ]
}}

Rules:
- Generate 5-7 technical_questions covering the job's required skills, spanning all three difficulty levels.
- Generate 4-5 behavioral_questions (situational, teamwork, ownership, conflict resolution, etc.).
- Generate 3-4 follow_up_questions, each tied to a specific skill the candidate lists on their resume
  (use "based_on_skill" to name it), that probe deeper into that skill.
- Base questions on the job's actual requirements and the candidate's actual skills/experience, not generic filler.
- Never invent skills the job or candidate doesn't have.

Job Title: {job_title}
Company: {company_name}
Required Skills: {job_skills}
Experience Required: {job_experience}
Education Required: {job_education}

Candidate Name: {candidate_name}
Candidate Skills: {candidate_skills}
Candidate Experience: {candidate_experience}
Candidate Education: {candidate_education}
Candidate Experience Details: {candidate_experience_details}
"""


def generate_interview_questions(job: dict, candidate: dict) -> dict:
    prompt = QUESTION_GEN_PROMPT.format(
        job_title=job.get("job_title") or "N/A",
        company_name=job.get("company_name") or "N/A",
        job_skills=", ".join(job.get("skills") or []) or "N/A",
        job_experience=job.get("experience") or "N/A",
        job_education=job.get("education") or "N/A",
        candidate_name=candidate.get("full_name") or "N/A",
        candidate_skills=", ".join(candidate.get("skills") or []) or "N/A",
        candidate_experience=candidate.get("experience_years") or "N/A",
        candidate_education=candidate.get("education") or "N/A",
        candidate_experience_details=(candidate.get("experience_details") or "N/A")[:2000],
    )
    data = _call_gemini_json(prompt)
    data.setdefault("technical_questions", [])
    data.setdefault("behavioral_questions", [])
    data.setdefault("follow_up_questions", [])
    return data


# ---------------------------------------------------------------------------
# Module 3 — AI-Powered Interview Simulation
# ---------------------------------------------------------------------------

EVALUATION_PROMPT = """You are an expert interview assessor. Evaluate the candidate's response to the
interview question below, in the context of the job they're interviewing for. Judge based only on the
written response text (no audio/video is available). Return ONLY valid JSON — no markdown fences, no
commentary — matching exactly this schema:

{{
  "relevance_score": number (0-100, how well the response answers the question and fits the role),
  "communication_feedback": string (1-2 sentences on clarity, structure, and confidence conveyed in the writing),
  "strengths": string (1-2 sentences on what the response did well),
  "improvements": string (1-2 sentences of specific, actionable improvement advice)
}}

Job Title: {job_title}
Required Skills: {job_skills}

Interview Question: {question}
Candidate Response: {response}
"""


def evaluate_interview_response(question: str, response_text: str, job: dict) -> dict:
    prompt = EVALUATION_PROMPT.format(
        job_title=job.get("job_title") or "N/A",
        job_skills=", ".join(job.get("skills") or []) or "N/A",
        question=question,
        response=response_text or "(no response provided)",
    )
    data = _call_gemini_json(prompt)
    data.setdefault("relevance_score", 0)
    data.setdefault("communication_feedback", "")
    data.setdefault("strengths", "")
    data.setdefault("improvements", "")
    return data


REPORT_PROMPT = """You are an expert interview assessor. Summarize this full mock-interview transcript
into an overall performance report for the recruiter. Return ONLY valid JSON — no markdown fences, no
commentary — matching exactly this schema:

{{
  "overall_score": number (0-100, weighted overall impression across all answers),
  "communication_feedback": string (2-3 sentences on overall clarity, confidence, and communication style),
  "strengths": string (2-3 sentences on the candidate's strongest points across the interview),
  "improvements": string (2-3 sentences of specific, actionable improvement advice for next time)
}}

Job Title: {job_title}

Transcript (question, response, per-question relevance score):
{transcript}
"""


def generate_performance_report(qa_transcript: list, job: dict) -> dict:
    transcript_text = "\n\n".join(
        f"Q: {item.get('question')}\nA: {item.get('response')}\nScore: {item.get('relevance_score')}"
        for item in qa_transcript
    ) or "(no responses recorded)"

    prompt = REPORT_PROMPT.format(
        job_title=job.get("job_title") or "N/A",
        transcript=transcript_text,
    )
    data = _call_gemini_json(prompt)
    data.setdefault("overall_score", 0)
    data.setdefault("communication_feedback", "")
    data.setdefault("strengths", "")
    data.setdefault("improvements", "")
    return data


# ---------------------------------------------------------------------------
# Milestone 4 — Voice-Based Screening
# ---------------------------------------------------------------------------

TRANSCRIBE_INSTRUCTION = (
    "Transcribe this audio recording exactly as spoken, in English. "
    "Return only the transcript text - no commentary, no timestamps, no speaker labels."
)


def _sniff_audio_mime(audio_bytes: bytes) -> str:
    """streamlit-mic-recorder's actual output format depends on the browser
    (wav, webm/opus, ogg...). Detect the real format from the file's magic
    bytes instead of guessing, so we always send Gemini the correct mime_type."""
    if not audio_bytes:
        return "audio/wav"
    head = audio_bytes[:16]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mp3"
    return "audio/wav"  # reasonable fallback guess


def transcribe_audio(audio_bytes: bytes, mime_type: str = None) -> str:
    """Transcribe a short voice recording using Gemini's audio understanding,
    so a candidate can answer an interview question by speaking instead of
    typing. Requires a Gemini model version that accepts audio input.

    Tries an inline-data request first (fast, no upload round-trip); if that
    fails for any reason, falls back to the File API, which Google's own
    docs recommend for audio/video and tends to be more reliable."""
    _ensure_configured()
    detected_mime = mime_type or _sniff_audio_mime(audio_bytes)
    model = genai.GenerativeModel(MODEL_NAME)

    inline_error = None
    try:
        response = model.generate_content([
            {"mime_type": detected_mime, "data": audio_bytes},
            TRANSCRIBE_INSTRUCTION,
        ])
        text = (response.text or "").strip()
        if text:
            return text
    except Exception as e:
        inline_error = e

    # Fallback: upload via the File API, then reference the uploaded file.
    try:
        import tempfile

        suffix = "." + detected_mime.split("/")[-1].split(";")[0]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        uploaded = genai.upload_file(tmp_path, mime_type=detected_mime)
        response = model.generate_content([uploaded, TRANSCRIBE_INSTRUCTION])
        return (response.text or "").strip()
    except Exception as file_api_error:
        raise RuntimeError(
            f"Inline audio request failed ({inline_error}); "
            f"File API fallback also failed ({file_api_error})"
        )

