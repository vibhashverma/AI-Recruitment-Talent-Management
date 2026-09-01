"""
tests/test_matching.py
Milestone 4, Module 3 — Testing Strategy.

Unit tests for matching.py's pure functions. These run standalone (no
PostgreSQL, no Gemini, no network) so they can be run on every commit.

Run with:  pytest tests/test_matching.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matching


# ---------------------------------------------------------------------------
# parse_experience_years
# ---------------------------------------------------------------------------

def test_parse_experience_years_single_number():
    assert matching.parse_experience_years("5 years") == 5.0


def test_parse_experience_years_range_takes_midpoint():
    assert matching.parse_experience_years("3-5 years") == 4.0


def test_parse_experience_years_none_when_no_number():
    assert matching.parse_experience_years("Fresher") is None


def test_parse_experience_years_none_when_empty():
    assert matching.parse_experience_years(None) is None
    assert matching.parse_experience_years("") is None


# ---------------------------------------------------------------------------
# compute_skill_match
# ---------------------------------------------------------------------------

def test_skill_match_full_overlap():
    result = matching.compute_skill_match(["Python", "SQL"], ["python", "sql"])
    assert result["skill_match_pct"] == 100.0
    assert result["missing_skills"] == []


def test_skill_match_partial_overlap():
    result = matching.compute_skill_match(["Python", "Docker"], ["Python", "SQL", "Kubernetes"])
    assert result["skill_match_pct"] == round(1 / 3 * 100, 1)
    assert "SQL" in result["missing_skills"]
    assert "Kubernetes" in result["missing_skills"]
    assert "Docker" in result["additional_skills"]


def test_skill_match_no_job_skills_is_neutral():
    result = matching.compute_skill_match(["Python"], [])
    assert result["skill_match_pct"] == 100.0
    assert result["skill_gap_pct"] == 0.0


# ---------------------------------------------------------------------------
# compute_experience_match
# ---------------------------------------------------------------------------

def test_experience_match_meets_requirement():
    assert matching.compute_experience_match("5 years", "3-5 years") == 100.0


def test_experience_match_below_requirement():
    score = matching.compute_experience_match("2 years", "4 years")
    assert score == 50.0


def test_experience_match_neutral_when_job_unspecified():
    assert matching.compute_experience_match("2 years", None) == 100.0


def test_experience_match_partial_credit_when_candidate_unknown():
    assert matching.compute_experience_match(None, "5 years") == 50.0


# ---------------------------------------------------------------------------
# compute_hiring_score — fixed weights: Skill 60 / Experience 25 / Education 10 / Certification 5
# ---------------------------------------------------------------------------

def test_hiring_score_all_perfect():
    assert matching.compute_hiring_score(100, 100, 100, 100) == 100.0


def test_hiring_score_weighted_correctly():
    score = matching.compute_hiring_score(skill_pct=80, experience_score=60, education_score=40, certification_score=20)
    expected = round(80 * 0.60 + 60 * 0.25 + 40 * 0.10 + 20 * 0.05, 1)
    assert score == expected


def test_hiring_score_zero_everything():
    assert matching.compute_hiring_score(0, 0, 0, 0) == 0.0


# ---------------------------------------------------------------------------
# rank_candidates_for_job
# ---------------------------------------------------------------------------

def test_rank_candidates_sorts_descending():
    job = {"skills": ["Python", "SQL"], "experience": "3 years", "education": None, "certification": None}
    candidates = [
        {"id": 1, "full_name": "Low Match", "skills": [], "experience_years": None, "education": None, "certifications": None},
        {"id": 2, "full_name": "High Match", "skills": ["Python", "SQL"], "experience_years": "5 years", "education": None, "certifications": None},
    ]
    results = matching.rank_candidates_for_job(candidates, job)
    assert results[0]["candidate_id"] == 2
    assert results[0]["hiring_score"] >= results[1]["hiring_score"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
