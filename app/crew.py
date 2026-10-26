"""The agents, their tasks, and how they are wired into CrewAI crews.

Interview prep (sequential, each task receives the previous outputs as context):

    Company Researcher -> Role Analyst -> Question Generator -> Answer Coach

Resume ATS review (one agent, fed the rule-based score from app/ats.py):

    ATS Resume Reviewer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from crewai import Agent, Crew, Process, Task

from app.tools import NewsSearchTool, ReadWebpageTool, WebSearchTool

NOT_PROVIDED = "(none provided)"
PREP_RESUME_CHARS = 3500  # keeps each prompt small enough for free-tier token limits
ATS_RESUME_CHARS = 6000
JD_CHARS = 3000


@dataclass(frozen=True)
class AgentSpec:
    key: str
    role: str
    icon: str
    summary: str  # one line shown on the agent's card
    goal: str
    backstory: str
    tools: tuple[str, ...] = field(default_factory=tuple)
    report_title: str = ""
    kind: str = "prep"  # which crew the agent belongs to: "prep" or "ats"
    reads: str = ""  # what the agent is given
    produces: str = ""  # what it hands on


AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        key="researcher",
        role="Company Researcher",
        icon="🏢",
        summary="Searches the web and news for facts about the company.",
        goal="Build an accurate, current brief on {company} that a candidate can use in an interview.",
        backstory=(
            "You are a business research analyst. You check several sources, prefer recent "
            "information, and never invent facts: if you cannot find something you say so."
        ),
        tools=("web_search", "news_search"),
        report_title="Company Brief",
        reads="Company, role and today's date",
        produces="Company brief with sources",
    ),
    AgentSpec(
        key="analyst",
        role="Role Analyst",
        icon="🧭",
        summary="Works out the skills and interview rounds for the role.",
        goal="Explain exactly what the {role} role at {company} demands and how candidates are interviewed.",
        backstory=(
            "You are a senior technical recruiter who has hired for this kind of role many times. "
            "You turn vague job ads into a clear list of skills and interview stages."
        ),
        tools=("web_search", "read_webpage"),
        report_title="Role Analysis",
        reads="Company brief, job description, resume",
        produces="Skills, interview rounds, gaps to prepare",
    ),
    AgentSpec(
        key="questioner",
        role="Question Generator",
        icon="❓",
        summary="Writes the questions this candidate is most likely to be asked.",
        goal="Predict the 10 interview questions a {experience} candidate for {role} at {company} is most likely to face.",
        backstory=(
            "You are an experienced interviewer at a top company. You write realistic, specific "
            "questions and you always explain what the interviewer is really testing."
        ),
        report_title="Likely Questions",
        reads="Brief, role analysis, resume",
        produces="10 likely questions",
    ),
    AgentSpec(
        key="coach",
        role="Answer Coach",
        icon="🎓",
        summary="Coaches model answers, tips and a 5-day prep plan.",
        goal="Help the candidate answer every question confidently and walk in fully prepared.",
        backstory=(
            "You are an interview coach. You teach the STAR method, keep answers concise and "
            "concrete, and tie answers back to facts about the company and the candidate's own resume."
        ),
        report_title="Answer Coaching",
        reads="Questions, brief, resume",
        produces="Answers, tips, 5-day plan",
    ),
)

ATS_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        key="ats_reviewer",
        role="ATS Resume Reviewer",
        icon="📄",
        summary="Turns the ATS findings into prioritised fixes and bullet rewrites.",
        goal="Raise the candidate's ATS score for {role} without inventing a single fact.",
        backstory=(
            "You are a resume coach who has screened thousands of resumes, both through ATS software and "
            "as a recruiter. You are strict about honesty: you improve wording and structure but never add "
            "employers, projects, tools or numbers the candidate did not provide."
        ),
        report_title="AI Review",
        kind="ats",
        reads="Resume, job description, ATS analysis",
        produces="Prioritised fixes and bullet rewrites",
    ),
)

ALL_SPECS: tuple[AgentSpec, ...] = AGENT_SPECS + ATS_SPECS
SPECS_BY_KIND = {"prep": AGENT_SPECS, "ats": ATS_SPECS}
SPEC_BY_ROLE = {spec.role: spec for spec in ALL_SPECS}

TASK_DESCRIPTIONS = {
    "researcher": (
        "Research {company} for a candidate interviewing for the {role} position. Today is {today}.\n"
        "Use web_search and news_search (at least 3 searches with different queries) to find:\n"
        "- what the company does: products or services, customers, business model\n"
        "- size, headquarters and where it operates\n"
        "- mission, values and work culture\n"
        "- notable news from roughly the last 12 months (launches, results, acquisitions, leadership changes)\n"
        "Only report facts found in the search results. If something is not found, say 'not found'."
    ),
    "analyst": (
        "Analyze the {role} role at {company} for a candidate with {experience} of experience.\n"
        "Job description supplied by the candidate (may be empty): {job_description}\n"
        "Candidate resume (may be empty): {resume}\n"
        "Before writing anything, call web_search at least twice: once for the interview process for "
        "{role} at {company} (rounds, formats, what each round focuses on) and once for the skills "
        "required. Use read_webpage on one promising result if useful. Combine what you find with the "
        "company brief. If a resume was provided, base 'Gaps to Prepare' on the difference between what "
        "the role needs and what the resume actually shows."
    ),
    "questioner": (
        "Using the company brief and the role analysis, write exactly 10 questions this candidate is "
        "most likely to be asked in an interview for {role} at {company}.\n"
        "Mix: 4 technical or role-specific, 3 behavioral, 3 company-specific (each company-specific "
        "question must reference a real fact from the company brief). Match the difficulty to a "
        "candidate with {experience} of experience.\n"
        "Candidate resume (may be empty): {resume}\n"
        "If a resume was provided, at least 3 of the 10 questions must probe specific projects, skills or "
        "experience that the resume states; start those questions with [Resume]. Never invent resume details."
    ),
    "coach": (
        "Coach the candidate on all 10 questions from the Question Generator for {role} at {company} "
        "(cover every one, Q1 to Q10, in order).\n"
        "For each question give a short model answer outline (use STAR for behavioral questions), one "
        "tip and one mistake to avoid. Ground company-specific answers in the company brief.\n"
        "Candidate resume (may be empty): {resume}\n"
        "If a resume was provided, build the model answers on the candidate's own projects and skills from "
        "it; use only what the resume says and never invent experience. Then suggest 3 smart questions to "
        "ask the interviewer and a 5-day preparation plan."
    ),
    "ats_reviewer": (
        "Review this resume the way an ATS and a recruiter would, for the target role: {role}.\n"
        "Resume:\n{resume}\n\n"
        "Job description (may be empty): {job_description}\n\n"
        "Automated ATS analysis (already computed, treat it as ground truth):\n{ats_summary}\n\n"
        "Fix what costs the candidate the most points first. Rewrite only bullets that exist in the resume. "
        "Never invent employers, projects, tools or numbers; where a metric is needed but unknown, write "
        "[add metric] instead of a made-up figure."
    ),
}

# Headings are listed on their own lines and the guidance comes after, because small models
# otherwise copy the guidance into the heading text.
EXPECTED_OUTPUTS = {
    "researcher": (
        "A Markdown company brief under 450 words, using exactly these headings:\n"
        "## Snapshot\n## Products & Business\n## Culture & Values\n## Recent News\n"
        "## Talking Points for the Interview\n"
        "Guidance (do not copy into headings): Snapshot has 3-5 bullets. Recent News has 2-4 bullets, "
        "each with a date if known and the source link. Talking Points has 3 bullets."
    ),
    "analyst": (
        "A Markdown role analysis under 400 words, using exactly these headings:\n"
        "## Role Summary\n## Must-Have Skills\n## Likely Interview Process\n"
        "## What Interviewers Look For\n## Gaps to Prepare\n"
        "Guidance (do not copy into headings): Role Summary is 2-3 sentences. Likely Interview Process "
        "is a numbered list of rounds and what each tests. The other sections are bullets."
    ),
    "questioner": (
        "Markdown with three sections: ## Technical / Role Questions, ## Behavioral Questions, "
        "## Company-Specific Questions. Number the questions 1 to 10 across all sections. Write each "
        "question in bold, followed by a line starting with '*Why they ask:*'."
    ),
    "coach": (
        "Markdown with: ## Answer Guide containing ### Q1 to ### Q10, each with **Model answer:** "
        "(3-5 bullets), **Tip:** and **Avoid:**; then ## Questions to Ask Them (3 bullets); then "
        "## 5-Day Prep Plan (Day 1 to Day 5)."
    ),
    "ats_reviewer": (
        "A Markdown review under 600 words, using exactly these headings:\n"
        "## Verdict\n## Top Fixes\n## Rewrite These Bullets\n## Keywords To Add\n## Improved Summary\n"
        "Guidance (do not copy into headings): Verdict is 2 sentences. Top Fixes is a numbered list of 5, "
        "each naming the score area it improves. Rewrite These Bullets shows the 4 weakest bullets from "
        "the resume as 'Before:' and 'After:' pairs. Keywords To Add lists only missing keywords that "
        "truthfully apply, each with where to add it (write 'none' if nothing applies). Improved Summary "
        "is 3 lines that use only facts from the resume."
    ),
}

TOOL_FACTORIES = {
    "web_search": WebSearchTool,
    "news_search": NewsSearchTool,
    "read_webpage": ReadWebpageTool,
}


def tool_info() -> list[dict[str, str]]:
    return [{"name": name, "description": factory().description} for name, factory in TOOL_FACTORIES.items()]


def build_inputs(
    company: str, role: str, experience: str, job_description: str = "", resume: str = ""
) -> dict[str, str]:
    return {
        "company": company.strip(),
        "role": role.strip(),
        "experience": experience.strip(),
        "job_description": job_description.strip()[:JD_CHARS] or NOT_PROVIDED,
        "resume": resume.strip()[:PREP_RESUME_CHARS] or NOT_PROVIDED,
        "today": date.today().isoformat(),
    }


def build_ats_inputs(resume: str, job_description: str, role: str, ats_summary: str) -> dict[str, str]:
    return {
        "resume": resume.strip()[:ATS_RESUME_CHARS],
        "job_description": job_description.strip()[:JD_CHARS] or NOT_PROVIDED,
        "role": role.strip() or "general applications",
        "ats_summary": ats_summary,
    }


def build_crew(llm, kind: str = "prep") -> Crew:
    """Create the agents and tasks of a crew. Inputs are filled in by crew.kickoff(inputs=...)."""
    agents: dict[str, Agent] = {}
    tasks: list[Task] = []
    for spec in SPECS_BY_KIND[kind]:
        agents[spec.key] = Agent(
            role=spec.role,
            goal=spec.goal,
            backstory=spec.backstory,
            tools=[TOOL_FACTORIES[name]() for name in spec.tools],
            llm=llm,
            allow_delegation=False,
            max_iter=8 if spec.tools else 3,
            verbose=False,
        )
        tasks.append(
            Task(
                name=spec.key,
                description=TASK_DESCRIPTIONS[spec.key],
                expected_output=EXPECTED_OUTPUTS[spec.key],
                agent=agents[spec.key],
                context=list(tasks),  # every earlier task's output is handed forward
            )
        )
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
    )
