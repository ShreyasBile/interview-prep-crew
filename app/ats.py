"""Rule-based ATS (applicant tracking system) resume scoring.

Scores a resume out of 100 across six areas, the same things most ATS parsers and recruiters
screen for. It needs no model, so results are instant and repeatable; the AI reviewer agent
turns the findings into concrete rewrites.

    Keyword match 35 | Sections 15 | Contact 10 | Impact 15 | Formatting 15 | Language 10

Without a job description the keyword area cannot be scored and the other areas are
rescaled to 100.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Any

MIN_WORDS = 40

SINGLE_WORD_SKILLS = (
    # languages
    "python java javascript typescript c++ c# golang rust kotlin swift php ruby scala matlab sql html css bash dart perl "
    # web and frameworks
    "react angular vue node.js express django flask fastapi spring .net asp.net next.js tailwind bootstrap jquery "
    "restful graphql microservices websockets "
    # data and ML
    "pandas numpy scikit-learn tensorflow pytorch keras nlp llm tableau excel statistics etl spark hadoop kafka airflow "
    # databases
    "mysql postgresql mongodb redis sqlite oracle nosql dynamodb elasticsearch firebase "
    # cloud and devops
    "aws azure gcp docker kubernetes terraform jenkins ci/cd linux git github gitlab devops ansible nginx serverless "
    # CS fundamentals and practices
    "oop dbms selenium junit pytest agile scrum jira cybersecurity blockchain iot embedded android ios flutter "
    # soft skills
    "communication teamwork leadership collaboration mentoring presentation analytical"
).split()

MULTI_WORD_SKILLS = (
    "r programming",
    "spring boot",
    "rest api",
    "data science",
    "data analysis",
    "data analytics",
    "data engineering",
    "data visualization",
    "machine learning",
    "deep learning",
    "computer vision",
    "generative ai",
    "power bi",
    "google cloud",
    "github actions",
    "cloud computing",
    "data structures",
    "object-oriented",
    "design patterns",
    "system design",
    "operating systems",
    "computer networks",
    "unit testing",
    "test automation",
    "penetration testing",
    "problem solving",
    "critical thinking",
    "time management",
    "stakeholder management",
)

# multi-word phrases first so "machine learning" is reported before the words inside it
SKILL_TERMS: tuple[str, ...] = tuple(dict.fromkeys((*MULTI_WORD_SKILLS, *SINGLE_WORD_SKILLS)))

STOPWORDS = frozenset(
    "a an the and or of to in on for with at by from as is are was were be been being this that these those it its "
    "your you our we they their them will would can could should may might must have has had do does did not no "
    "if then than so such into over under about up out more most other some any all each per via also etc within "
    "across including include includes who which what when where how both either".split()
)
GENERIC = frozenset(
    "experience experienced ability able strong knowledge skills skill work working works team teams years year "
    "required requirements requirement preferred role position job candidate candidates responsibilities responsibility "
    "looking join company new good excellent plus ideal opportunity environment business related relevant "
    "understanding using use used well high based help support develop development building build "
    "responsible duties qualifications degree bachelor master equivalent minimum least".split()
)

ACTION_VERBS = frozenset(
    "accelerated achieved analyzed analysed architected automated boosted built collaborated configured consolidated "
    "contributed converted coordinated created cut debugged decreased delivered deployed designed developed directed "
    "documented drove eliminated enhanced established evaluated executed expanded facilitated generated guided "
    "identified implemented improved increased initiated integrated introduced investigated launched led maintained "
    "managed mentored migrated modernized monitored negotiated optimized organized orchestrated oversaw owned "
    "partnered performed pioneered planned presented prioritized produced programmed published reduced refactored "
    "released resolved restructured reviewed scaled secured shipped simplified solved spearheaded standardized "
    "streamlined strengthened supervised tested trained transformed troubleshot upgraded validated won wrote "
    "built build led lead ran run won win cut taught teach drove drive wrote write".split()
)
WEAK_PHRASES = (
    "responsible for",
    "duties included",
    "worked on",
    "helped with",
    "helped in",
    "assisted in",
    "assisted with",
    "tasked with",
    "participated in",
    "involved in",
    "in charge of",
)

SECTION_PATTERNS = {
    "summary": r"(professional\s+|career\s+)?(summary|profile|objective|about(\s+me)?)",
    "experience": r"(work\s+|professional\s+|relevant\s+)?(experience|employment(\s+history)?|internships?)",
    "education": r"(education|academics?|academic\s+(background|qualifications?))",
    "skills": r"(technical\s+|key\s+|core\s+)?(skills|competencies|technologies|tech\s+stack)",
    "projects": r"(academic\s+|personal\s+|key\s+)?projects?",
    "certifications": r"(certifications?|licenses?|courses|achievements|awards|honou?rs)",
}
SECTION_RES = {k: re.compile(rf"^\s*{v}\s*:?\s*$", re.I) for k, v in SECTION_PATTERNS.items()}

BULLET_RE = re.compile(r"^\s*[•\-–—*▪►>]\s+(\S.*)$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d{1,3}[\s.-]?)?(\(?\d{3,5}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{4,5}(?!\d)")
LINK_RE = re.compile(r"linkedin\.com/\S+|github\.com/\S+|https?://\S+|www\.\S+|portfolio", re.I)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
NUMBER_RE = re.compile(r"(?<![\w.])(?!(?:19|20)\d{2}\b)\d[\d,.]*(?![\w])|%|\$\s?\d|₹\s?\d")
PRONOUN_RE = re.compile(r"(?<![\w/.])I(?![\w/.'])|\b[Mm]y\b|\b[Mm]e\b")

STATUS_PASS, STATUS_WARN, STATUS_FAIL = "pass", "warn", "fail"


def check(status: str, title: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "title": title, "detail": detail}


def term_regex(term: str) -> re.Pattern[str]:
    return _term_regex(term.lower())


@lru_cache(maxsize=512)
def _term_regex(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w+#.]){re.escape(term)}(?:s|es)?(?![\w+#])", re.I)


def has_term(text: str, term: str) -> bool:
    return term_regex(term).search(text) is not None


def skills_in(text: str) -> list[str]:
    return [skill for skill in SKILL_TERMS if has_term(text, skill)]


def job_keywords(job_description: str, limit: int = 25) -> list[str]:
    """Known skills first, then repeated meaningful words from the job description."""
    jd = job_description.lower()
    terms = [s for s in SKILL_TERMS if has_term(jd, s)][:20]
    words = re.findall(r"[a-z][a-z0-9+#.\-]{2,}", jd)
    counts = Counter(
        w.strip(".-")
        for w in words
        if w.strip(".-") not in STOPWORDS and w.strip(".-") not in GENERIC and len(w.strip(".-")) >= 4
    )
    covered = " ".join(terms)
    for word, count in counts.most_common():
        if len(terms) >= limit:
            break
        if count >= 2 and word not in covered and word not in terms:
            terms.append(word)
    return terms[:limit]


def tokenize_stats(text: str) -> dict[str, Any]:
    words = re.findall(r"[\w][\w'+#.\-/]*", text)
    return {"words": len(words), "pages": round(len(words) / 500, 1)}


def find_sections(lines: list[str]) -> set[str]:
    found = set()
    for line in lines:
        if 0 < len(line.strip()) <= 40:
            for name, pattern in SECTION_RES.items():
                if pattern.match(line):
                    found.add(name)
    return found


def bullet_lines(lines: list[str]) -> list[str]:
    return [m.group(1).strip() for line in lines if (m := BULLET_RE.match(line))]


def is_action_verb(word: str) -> bool:
    w = word.lower().strip(".,;:")
    return w in ACTION_VERBS or w + "d" in ACTION_VERBS or w + "ed" in ACTION_VERBS


# ---------- scoring areas: each returns (score, max, checks) ----------


def score_keywords(text: str, job_description: str) -> tuple[float, float, list[dict], dict]:
    terms = job_keywords(job_description)
    if not terms:
        return 0, 35, [check(STATUS_WARN, "Job description has too few keywords to compare")], {"matched": [], "missing": []}
    matched = [t for t in terms if has_term(text, t)]
    missing = [t for t in terms if t not in matched]
    ratio = len(matched) / len(terms)
    score = round(35 * min(1.0, ratio / 0.8), 1)  # 80% of the keywords earns full marks
    status = STATUS_PASS if ratio >= 0.7 else STATUS_WARN if ratio >= 0.4 else STATUS_FAIL
    checks = [check(status, f"{len(matched)} of {len(terms)} job keywords found ({ratio:.0%})")]
    if missing:
        checks.append(check(STATUS_WARN, "Missing keywords", ", ".join(missing[:8])))
    return score, 35, checks, {"matched": matched, "missing": missing}


def score_sections(lines: list[str]) -> tuple[float, float, list[dict]]:
    found = find_sections(lines)
    checks, score = [], 0.0
    plan = (
        ("education", 4, "Education section"),
        ("skills", 4, "Skills section"),
        ("summary", 2, "Summary or objective"),
        ("certifications", 1, "Certifications, courses or awards"),
    )
    for key, points, title in plan:
        if key in found:
            score += points
            checks.append(check(STATUS_PASS, f"{title} found"))
        else:
            checks.append(check(STATUS_FAIL if points >= 4 else STATUS_WARN, f"{title} missing", "Use a standard heading so parsers can find it."))
    if "experience" in found or "projects" in found:
        score += 4
        label = "Experience" if "experience" in found else "Projects"
        checks.append(check(STATUS_PASS, f"{label} section found"))
    else:
        checks.append(check(STATUS_FAIL, "No Experience or Projects section", "Add one with a standard heading."))
    return score, 15, checks


def score_contact(text: str) -> tuple[float, float, list[dict]]:
    checks, score = [], 0.0
    if EMAIL_RE.search(text):
        score += 4
        checks.append(check(STATUS_PASS, "Email address found"))
    else:
        checks.append(check(STATUS_FAIL, "No email address", "Recruiters and ATS forms need one."))
    if PHONE_RE.search(text):
        score += 3
        checks.append(check(STATUS_PASS, "Phone number found"))
    else:
        checks.append(check(STATUS_WARN, "No phone number"))
    if LINK_RE.search(text):
        score += 3
        checks.append(check(STATUS_PASS, "LinkedIn, GitHub or portfolio link found"))
    else:
        checks.append(check(STATUS_WARN, "No LinkedIn, GitHub or portfolio link"))
    return score, 10, checks


def score_impact(bullets: list[str]) -> tuple[float, float, list[dict], dict]:
    stats = {"bullets": len(bullets), "quantified": 0, "action_verbs": 0}
    if len(bullets) < 3:
        checks = [check(STATUS_FAIL, "Few or no bullet points", "Describe achievements as short bullets starting with a verb.")]
        return 0, 15, checks, stats
    quantified = sum(1 for b in bullets if NUMBER_RE.search(b))
    action = sum(1 for b in bullets if is_action_verb(b.split()[0]))
    stats.update(quantified=quantified, action_verbs=action)
    q_ratio, a_ratio = quantified / len(bullets), action / len(bullets)
    score = round(8 * min(1.0, q_ratio / 0.3) + 7 * min(1.0, a_ratio / 0.6), 1)
    checks = [
        check(
            STATUS_PASS if q_ratio >= 0.3 else STATUS_WARN if q_ratio >= 0.15 else STATUS_FAIL,
            f"{quantified} of {len(bullets)} bullets include numbers ({q_ratio:.0%})",
            "" if q_ratio >= 0.3 else "Add metrics: percentages, counts, time saved, users, revenue.",
        ),
        check(
            STATUS_PASS if a_ratio >= 0.6 else STATUS_WARN if a_ratio >= 0.35 else STATUS_FAIL,
            f"{action} of {len(bullets)} bullets start with an action verb ({a_ratio:.0%})",
            "" if a_ratio >= 0.6 else "Start bullets with verbs like built, led, reduced, automated.",
        ),
    ]
    return score, 15, checks, stats


def score_formatting(text: str, lines: list[str], bullets_raw: list[str], words: int) -> tuple[float, float, list[dict]]:
    checks, score = [], 0.0
    if 350 <= words <= 800:
        score += 6
        checks.append(check(STATUS_PASS, f"Length is {words} words", "About one page; ideal for most roles."))
    elif 250 <= words < 350 or 800 < words <= 1000:
        score += 4
        checks.append(check(STATUS_WARN, f"Length is {words} words", "Aim for 350 to 800 words (one to two pages)."))
    elif 150 <= words < 250 or 1000 < words <= 1300:
        score += 2
        checks.append(check(STATUS_WARN, f"Length is {words} words", "Aim for 350 to 800 words (one to two pages)."))
    else:
        checks.append(check(STATUS_FAIL, f"Length is {words} words", "Aim for 350 to 800 words (one to two pages)."))
    long_lines = sum(1 for line in lines if len(line) > 220)
    if long_lines == 0:
        score += 3
        checks.append(check(STATUS_PASS, "No walls of text"))
    else:
        score += 1.5 if long_lines <= 2 else 0
        checks.append(check(STATUS_WARN, f"{long_lines} very long line(s)", "Break long paragraphs into bullets."))
    years = len(YEAR_RE.findall(text))
    if years >= 2:
        score += 3
        checks.append(check(STATUS_PASS, "Dates found"))
    else:
        score += 1.5 if years == 1 else 0
        checks.append(check(STATUS_WARN, "Few dates", "Add start and end dates to education and experience."))
    glyphs = {line.lstrip()[0] for line in lines if BULLET_RE.match(line)}
    if len(glyphs) == 1:
        score += 3
        checks.append(check(STATUS_PASS, "Consistent bullet style"))
    elif len(glyphs) == 2:
        score += 1.5
        checks.append(check(STATUS_WARN, "Mixed bullet styles", "Use one bullet style throughout."))
    else:
        checks.append(check(STATUS_WARN, "No consistent bullet style found"))
    return score, 15, checks


def score_language(text: str, bullets: list[str]) -> tuple[float, float, list[dict]]:
    lowered = text.lower()
    weak = [p for p in WEAK_PHRASES if p in lowered]
    pronouns = len(PRONOUN_RE.findall(text))
    openers = Counter(b.split()[0].lower() for b in bullets if b.split())
    repeated = [w for w, n in openers.items() if n >= 4 and n / max(len(bullets), 1) >= 0.3]
    score = 10 - 2 * min(3, len(weak)) - (2 if pronouns >= 2 else 0) - (2 if repeated else 0)
    checks = []
    if weak:
        checks.append(check(STATUS_WARN, f"Weak phrases: {', '.join(weak[:4])}", "Replace with a strong verb and a result."))
    else:
        checks.append(check(STATUS_PASS, "No weak phrases like 'responsible for'"))
    if pronouns >= 2:
        checks.append(check(STATUS_WARN, "First-person pronouns (I, my)", "Resumes read better without them."))
    else:
        checks.append(check(STATUS_PASS, "No first-person pronouns"))
    if repeated:
        checks.append(check(STATUS_WARN, f"'{repeated[0].title()}' starts many bullets", "Vary your opening verbs."))
    return max(0.0, float(score)), 10, checks


# ---------- public API ----------


def grade(score: int) -> str:
    return "Excellent" if score >= 80 else "Good" if score >= 65 else "Needs work" if score >= 50 else "Weak"


def analyze(resume: str, job_description: str = "") -> dict[str, Any]:
    text = resume.strip()
    if len(text.split()) < MIN_WORDS:
        raise ValueError(f"Resume looks too short to score (needs at least {MIN_WORDS} words).")
    lines = text.split("\n")
    bullets = bullet_lines(lines)
    base = tokenize_stats(text)
    has_jd = bool(job_description.strip())

    areas: list[dict[str, Any]] = []
    keywords: dict[str, Any] = {"matched": [], "missing": [], "skills_found": skills_in(text)}
    if has_jd:
        score, maximum, checks, found = score_keywords(text, job_description)
        keywords.update(found)
        areas.append({"key": "keywords", "label": "Keyword match", "score": score, "max": maximum, "checks": checks})
    for key, label, result in (
        ("sections", "Sections", score_sections(lines)),
        ("contact", "Contact info", score_contact(text)),
    ):
        areas.append({"key": key, "label": label, "score": result[0], "max": result[1], "checks": result[2]})
    impact_score, impact_max, impact_checks, impact_stats = score_impact(bullets)
    areas.append({"key": "impact", "label": "Impact", "score": impact_score, "max": impact_max, "checks": impact_checks})
    fmt = score_formatting(text, lines, bullets, base["words"])
    areas.append({"key": "formatting", "label": "Formatting", "score": fmt[0], "max": fmt[1], "checks": fmt[2]})
    lang = score_language(text, bullets)
    areas.append({"key": "language", "label": "Language", "score": lang[0], "max": lang[1], "checks": lang[2]})

    total, maximum = sum(a["score"] for a in areas), sum(a["max"] for a in areas)
    overall = round(100 * total / maximum)
    for a in areas:
        a["score"] = round(a["score"], 1)
    return {
        "score": overall,
        "grade": grade(overall),
        "has_job_description": has_jd,
        "areas": areas,
        "keywords": keywords,
        "stats": {
            "words": base["words"],
            "pages": base["pages"],
            "bullets": impact_stats["bullets"],
            "quantified": impact_stats["quantified"],
            "action_verbs": impact_stats["action_verbs"],
            "skills": len(keywords["skills_found"]),
        },
    }


def summarize(result: dict[str, Any]) -> str:
    """A short text version of the analysis, handed to the AI reviewer agent."""
    weak = sorted(result["areas"], key=lambda a: a["score"] / a["max"])[:3]
    lines = [f"ATS score {result['score']}/100 ({result['grade']})."]
    lines.append("Weakest areas: " + "; ".join(f"{a['label']} {a['score']}/{a['max']}" for a in weak) + ".")
    problems = [
        f"{a['label']}: {c['title']}" + (f" ({c['detail']})" if c["detail"] else "")
        for a in result["areas"]
        for c in a["checks"]
        if c["status"] != STATUS_PASS
    ]
    if problems:
        lines.append("Issues found: " + " | ".join(problems[:10]))
    missing = result["keywords"]["missing"]
    if missing:
        lines.append("Job keywords missing from the resume: " + ", ".join(missing[:12]) + ".")
    return "\n".join(lines)
