import json

import pytest

from app import ats
from tests.samples import GOOD_RESUME, JOB_DESCRIPTION, POOR_RESUME

MEDIUM_RESUME = """Riya Patel
riya.patel@example.com

EDUCATION
B.Sc Information Technology, Mumbai University, 2021 - 2024

SKILLS
Python, SQL, Excel

EXPERIENCE
Data Intern, Brightwave Analytics, Jan 2024 - Jun 2024
- Responsible for cleaning data and preparing weekly reports for the sales team
- Worked on dashboards in Excel and helped with SQL queries
- Assisted in testing a small forecasting script written in Python
- Prepared slides for the monthly review meeting with the regional managers
- Maintained spreadsheets used by the finance team to track expenses and invoices every week
"""


def area(result, key):
    return next(a for a in result["areas"] if a["key"] == key)


def status_of(result, key, title_part):
    return next(c["status"] for c in area(result, key)["checks"] if title_part in c["title"])


def test_strong_resume_scores_excellent():
    result = ats.analyze(GOOD_RESUME, JOB_DESCRIPTION)
    assert result["score"] >= 90 and result["grade"] == "Excellent"
    assert all(a["score"] >= 0.8 * a["max"] for a in result["areas"])


def test_poor_resume_scores_weak_with_clear_findings():
    result = ats.analyze(POOR_RESUME, JOB_DESCRIPTION)
    assert result["score"] < 20 and result["grade"] == "Weak"
    assert status_of(result, "contact", "email") == "fail"
    assert status_of(result, "sections", "Education") == "fail"
    assert "responsible for" in " ".join(c["title"] for c in area(result, "language")["checks"])
    assert status_of(result, "language", "pronouns") == "warn"


def test_scores_order_poor_below_medium_below_strong():
    poor = ats.analyze(POOR_RESUME, JOB_DESCRIPTION)["score"]
    medium = ats.analyze(MEDIUM_RESUME, JOB_DESCRIPTION)["score"]
    strong = ats.analyze(GOOD_RESUME, JOB_DESCRIPTION)["score"]
    assert poor < medium < strong


def test_job_keywords_are_split_into_matched_and_missing():
    keywords = ats.analyze(GOOD_RESUME, JOB_DESCRIPTION)["keywords"]
    assert {"python", "fastapi", "postgresql", "docker", "kubernetes", "aws", "ci/cd", "rest api"} <= set(keywords["matched"])
    assert set(keywords["missing"]) == {"kafka", "graphql"}


def test_without_a_job_description_keywords_are_skipped_and_score_is_rescaled():
    result = ats.analyze(GOOD_RESUME)
    assert result["has_job_description"] is False
    assert [a["key"] for a in result["areas"]] == ["sections", "contact", "impact", "formatting", "language"]
    assert sum(a["max"] for a in result["areas"]) == 65
    assert result["score"] >= 90
    assert "python" in result["keywords"]["skills_found"]  # skills are still detected


def test_too_short_resume_is_rejected():
    with pytest.raises(ValueError, match="too short"):
        ats.analyze("Just a few words here")


def test_result_is_json_serialisable_and_deterministic():
    first = ats.analyze(GOOD_RESUME, JOB_DESCRIPTION)
    assert json.loads(json.dumps(first)) == first
    assert ats.analyze(GOOD_RESUME, JOB_DESCRIPTION) == first


def test_area_scores_never_exceed_their_maximum():
    for resume in (GOOD_RESUME, MEDIUM_RESUME, POOR_RESUME):
        for a in ats.analyze(resume, JOB_DESCRIPTION)["areas"]:
            assert 0 <= a["score"] <= a["max"]


@pytest.mark.parametrize(
    "heading, section",
    [
        ("WORK EXPERIENCE", "experience"),
        ("Technical Skills:", "skills"),
        ("Education", "education"),
        ("Professional Summary", "summary"),
        ("Academic Projects", "projects"),
        ("Certifications", "certifications"),
    ],
)
def test_common_section_headings_are_recognised(heading, section):
    assert section in ats.find_sections(["Some Name", heading, "content"])


def test_ordinary_sentences_are_not_mistaken_for_headings():
    assert ats.find_sections(["I have experience with many education tools in my skills"]) == set()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Built 12 endpoints", True),
        ("Cut costs by 30%", True),
        ("Saved $5,000 a month", True),
        ("Graduated in 2023", False),  # a year is not a metric
        ("Helped the team", False),
    ],
)
def test_numbers_count_as_metrics_but_years_do_not(text, expected):
    assert bool(ats.NUMBER_RE.search(text)) is expected


@pytest.mark.parametrize("word", ["Developed", "built", "Led", "manage", "Optimized", "reduced"])
def test_action_verbs_are_recognised(word):
    assert ats.is_action_verb(word)


@pytest.mark.parametrize("word", ["Responsible", "Helped", "Various", "The"])
def test_weak_openers_are_not_action_verbs(word):
    assert not ats.is_action_verb(word)


@pytest.mark.parametrize(
    "text, term, found",
    [
        ("Experienced in JavaScript", "java", False),  # java must not match inside javascript
        ("Wrote C++ and C# code", "c++", True),
        ("Wrote C++ and C# code", "c#", True),
        ("Built apps with Node.js", "node.js", True),
        ("Designed REST APIs", "rest api", True),  # plural forms match
        ("Used CI/CD pipelines", "ci/cd", True),
        ("Knows .NET well", ".net", True),
        ("Studied scalability", "scala", False),
    ],
)
def test_keyword_matching_respects_word_boundaries(text, term, found):
    assert ats.has_term(text, term) is found


def test_frequent_job_words_become_keywords_but_filler_does_not():
    jd = "Build data pipelines. Own pipelines end to end. Strong experience required. Experience with warehousing and warehousing tools."
    keywords = ats.job_keywords(jd)
    assert "pipelines" in keywords and "warehousing" in keywords
    assert "experience" not in keywords and "strong" not in keywords


def test_contact_details_are_detected():
    score, maximum, checks = ats.score_contact("Call +91 98765 43210 or mail me@site.com, see linkedin.com/in/me")
    assert score == maximum == 10
    score, _, checks = ats.score_contact("nothing useful here")
    assert score == 0 and all(c["status"] != "pass" for c in checks)


def test_summary_text_names_weak_areas_and_missing_keywords():
    text = ats.summarize(ats.analyze(POOR_RESUME, JOB_DESCRIPTION))
    assert text.startswith("ATS score ")
    assert "Weakest areas" in text and "kafka" in text
