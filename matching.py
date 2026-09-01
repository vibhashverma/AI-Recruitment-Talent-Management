"""
matching.py
Milestone 2 — Matching & Skill Analysis.

Compares a candidate profile against a job posting to produce:
- Matched / Missing / Additional skills
- Skill match % and skill gap %
- Experience match score
- Education match score
- An overall weighted Hiring Score
- Plain-language recommendations for closing skill gaps
"""

import re
from typing import List, Optional


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_experience_years(text: Optional[str]) -> Optional[float]:
    """Extract a representative number of years from free text.

    '5 years' -> 5.0, '3-5 years' -> 4.0 (midpoint), '5+ years' -> 5.0.
    Returns None if no number is found.
    """
    if not text:
        return None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if len(numbers) >= 2:
        return sum(numbers[:2]) / 2
    return numbers[0]


def _normalize_skills(skills) -> dict:
    """Return {lowercased_skill: original_label}, first-seen casing wins."""
    mapping = {}
    for s in skills or []:
        s = (s or "").strip()
        if not s:
            continue
        mapping.setdefault(s.lower(), s)
    return mapping


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------

def compute_skill_match(candidate_skills, job_skills) -> dict:
    cand_map = _normalize_skills(candidate_skills)
    job_map = _normalize_skills(job_skills)

    cand_keys = set(cand_map.keys())
    job_keys = set(job_map.keys())

    matched_keys = job_keys & cand_keys
    missing_keys = job_keys - cand_keys
    additional_keys = cand_keys - job_keys

    matched = [job_map[k] for k in sorted(matched_keys)]
    missing = [job_map[k] for k in sorted(missing_keys)]
    additional = [cand_map[k] for k in sorted(additional_keys)]

    match_pct = (len(matched) / len(job_keys) * 100) if job_keys else 100.0
    gap_pct = 100.0 - match_pct

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "additional_skills": additional,
        "skill_match_pct": round(match_pct, 1),
        "skill_gap_pct": round(gap_pct, 1),
    }


def compute_experience_match(candidate_experience: Optional[str], job_experience: Optional[str]) -> float:
    """0-100 score. Neutral (100) if the job has no parseable requirement."""
    required = parse_experience_years(job_experience)
    have = parse_experience_years(candidate_experience)

    if required is None or required <= 0:
        return 100.0
    if have is None:
        return 50.0  # unknown candidate experience: partial credit, not a hard penalty

    if have >= required:
        return 100.0
    return round(max(0.0, have / required) * 100, 1)


def compute_education_match(candidate_education: Optional[str], job_education: Optional[str]) -> float:
    """Lightweight keyword-overlap heuristic. 0-100."""
    if not job_education:
        return 100.0
    if not candidate_education:
        return 50.0

    job_words = {w for w in re.findall(r"[a-zA-Z]+", job_education.lower()) if len(w) > 2}
    cand_words = {w for w in re.findall(r"[a-zA-Z]+", candidate_education.lower()) if len(w) > 2}

    if not job_words:
        return 100.0
    overlap = job_words & cand_words
    return round((len(overlap) / len(job_words)) * 100, 1) if overlap else 40.0


def compute_certification_match(candidate_certifications: Optional[str], job_certification: Optional[str]) -> float:
    """Lightweight keyword-overlap heuristic. 0-100. Neutral if the job asks for none."""
    if not job_certification:
        return 100.0
    if not candidate_certifications:
        return 30.0  # job explicitly wants a certification and candidate lists none

    job_words = {w for w in re.findall(r"[a-zA-Z]+", job_certification.lower()) if len(w) > 2}
    cand_words = {w for w in re.findall(r"[a-zA-Z]+", candidate_certifications.lower()) if len(w) > 2}

    if not job_words:
        return 100.0
    overlap = job_words & cand_words
    return round((len(overlap) / len(job_words)) * 100, 1) if overlap else 30.0


# ---------------------------------------------------------------------------
# Hiring score + recommendations
# ---------------------------------------------------------------------------

def compute_hiring_score(skill_pct: float, experience_score: float, education_score: float,
                          certification_score: float) -> float:
    """Fixed weighted blend:
       Skill 60% + Experience 25% + Education 10% + Certification 5%.
    Each component is already neutral (100) when the job doesn't specify
    that requirement, so the weights stay fixed regardless."""
    W_SKILL, W_EXPERIENCE, W_EDUCATION, W_CERTIFICATION = 0.60, 0.25, 0.10, 0.05
    score = (
        skill_pct * W_SKILL
        + experience_score * W_EXPERIENCE
        + education_score * W_EDUCATION
        + certification_score * W_CERTIFICATION
    )
    return round(score, 1)


def generate_recommendations(missing_skills: List[str]) -> List[str]:
    if not missing_skills:
        return ["No skill gaps found — candidate meets all listed skill requirements."]
    preview = ", ".join(missing_skills[:5])
    more = f", and {len(missing_skills) - 5} more" if len(missing_skills) > 5 else ""
    return [
        f"Focus on building proficiency in: {preview}{more}.",
        "Relevant certifications, short courses, or hands-on projects can help close these gaps.",
    ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def match_candidate_to_job(candidate: dict, job: dict) -> dict:
    skill_result = compute_skill_match(candidate.get("skills"), job.get("skills"))
    experience_score = compute_experience_match(candidate.get("experience_years"), job.get("experience"))
    education_score = compute_education_match(candidate.get("education"), job.get("education"))
    certification_score = compute_certification_match(candidate.get("certifications"), job.get("certification"))
    hiring_score = compute_hiring_score(
        skill_result["skill_match_pct"],
        experience_score,
        education_score,
        certification_score,
    )

    return {
        "candidate_id": candidate.get("id"),
        "full_name": candidate.get("full_name"),
        "email": candidate.get("email"),
        "hiring_score": hiring_score,
        "experience_match_score": experience_score,
        "education_match_score": education_score,
        "certification_match_score": certification_score,
        "recommendations": generate_recommendations(skill_result["missing_skills"]),
        **skill_result,
    }


def rank_candidates_for_job(candidates: List[dict], job: dict) -> List[dict]:
    """Score every candidate against the job and rank descending by hiring score."""
    results = [match_candidate_to_job(c, job) for c in candidates]
    results.sort(key=lambda r: r["hiring_score"], reverse=True)
    return results
