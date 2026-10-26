from string import Formatter

from app.crew import (
    AGENT_SPECS,
    ALL_SPECS,
    EXPECTED_OUTPUTS,
    TASK_DESCRIPTIONS,
    build_ats_inputs,
    build_crew,
    build_inputs,
)
from tests.fake_llm import ScriptedLLM


def placeholders(text):
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_crew_has_four_agents_in_pipeline_order():
    crew = build_crew(ScriptedLLM())
    assert [a.role for a in crew.agents] == ["Company Researcher", "Role Analyst", "Question Generator", "Answer Coach"]
    assert crew.process.value == "sequential"


def test_research_agents_have_their_tools():
    crew = build_crew(ScriptedLLM())
    tools = {a.role: sorted(t.name for t in a.tools) for a in crew.agents}
    assert tools == {
        "Company Researcher": ["news_search", "web_search"],
        "Role Analyst": ["read_webpage", "web_search"],
        "Question Generator": [],
        "Answer Coach": [],
    }


def test_agents_with_tools_never_have_exactly_one():
    # With a single tool CrewAI forces tool_choice, which current Claude models reject (400).
    for spec in AGENT_SPECS:
        assert len(spec.tools) != 1, spec.role


def test_each_task_gets_all_earlier_outputs_as_context():
    crew = build_crew(ScriptedLLM())
    for i, task in enumerate(crew.tasks):
        assert task.context == crew.tasks[:i]
        assert task.agent is crew.agents[i]


def test_every_placeholder_is_filled_by_build_inputs():
    available = set(build_inputs("Acme", "Analyst", "1-3 years")) | set(build_ats_inputs("cv", "jd", "Analyst", "summary"))
    texts = list(TASK_DESCRIPTIONS.values()) + list(EXPECTED_OUTPUTS.values())
    texts += [s.goal for s in ALL_SPECS] + [s.backstory for s in ALL_SPECS]
    for text in texts:
        assert placeholders(text) <= available, text[:60]


def test_build_inputs_trims_and_fills_defaults():
    inputs = build_inputs("  Acme ", " Analyst ", "Fresher / intern", "   ")
    assert inputs["company"] == "Acme"
    assert inputs["role"] == "Analyst"
    assert inputs["job_description"] == "(none provided)"
    assert len(inputs["today"]) == 10
