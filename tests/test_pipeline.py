"""End-to-end: the real CrewAI crew, driven by the scripted LLM, through our event bridge."""


from app.crew import AGENT_SPECS, build_inputs
from app.events import EventBridge
from app.runs import RunManager, coalesce
from tests.conftest import wait_until_done
from tests.fake_llm import ScriptedLLM

KEYS = [s.key for s in AGENT_SPECS]


def make_manager(tmp_path, **llm_kwargs):
    bridge = EventBridge()
    bridge.install()
    return RunManager(bridge, lambda: ScriptedLLM(**llm_kwargs), "fake/scripted")


def first_index(events, type_, agent=None):
    for i, ev in enumerate(events):
        if ev["type"] == type_ and (agent is None or ev.get("agent") == agent):
            return i
    raise AssertionError(f"no {type_} event for {agent}")


def test_full_run_reports_every_agent_step(tmp_path, fake_search):
    manager = make_manager(tmp_path)
    run = wait_until_done(manager.start_prep(build_inputs("Acme Corp", "Data Analyst", "1-3 years")))

    assert run.status == "completed", run.error
    events = run.events
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"
    assert [a["key"] for a in events[0]["agents"]] == KEYS

    for key in KEYS:
        start = first_index(events, "agent_started", key)
        llm = first_index(events, "llm_started", key)
        chunk = first_index(events, "llm_chunk", key)
        done = first_index(events, "task_completed", key)
        assert start < llm < chunk < done

    # the two research agents really called their search tool and saw the results
    for key in ("researcher", "analyst"):
        started = events[first_index(events, "tool_started", key)]
        finished = events[first_index(events, "tool_finished", key)]
        assert started["tool"] == "web_search" and "Acme" in started["args"]["query"]
        assert "acme.example/careers" in finished["output"]

    # sequential hand-off: each agent starts only after the previous one finished
    for prev, nxt in zip(KEYS, KEYS[1:]):
        assert first_index(events, "task_completed", prev) < first_index(events, "agent_started", nxt)

    # the next agent's prompt contains the previous agent's output (CrewAI task context)
    analyst_prompt = events[first_index(events, "agent_started", "analyst")]["task_prompt"]
    assert "Acme Corp builds analytics software" in analyst_prompt

    assert set(run.report) == set(KEYS)
    assert run.report["coach"].startswith("## Answer Guide")
    final = events[-1]["report"]
    assert final == run.report
    md = run.to_markdown()
    assert "# Interview Prep: Data Analyst at Acme Corp" in md and "Answer Coaching" in md


def test_events_are_numbered_in_order(tmp_path, fake_search):
    run = wait_until_done(make_manager(tmp_path).start_prep(build_inputs("Acme", "Analyst", "1-3 years")))
    assert [e["seq"] for e in run.events] == list(range(1, len(run.events) + 1))


def test_streamed_chunks_rebuild_the_full_reply(tmp_path, fake_search):
    run = wait_until_done(make_manager(tmp_path).start_prep(build_inputs("Acme", "Analyst", "1-3 years")))
    merged = coalesce(run.events)
    assert len(merged) < len(run.events)
    coach_text = "".join(e["text"] for e in merged if e["type"] == "llm_chunk" and e["agent"] == "coach")
    assert "Final Answer: ## Answer Guide" in coach_text


def test_clean_run_has_no_warnings(tmp_path, fake_search):
    run = wait_until_done(make_manager(tmp_path).start_prep(build_inputs("Acme", "Analyst", "1-3 years")))
    assert run.warnings == []
    assert run.events[-1]["warnings"] == []


def test_cut_off_reply_is_flagged_not_passed_off_as_complete(tmp_path, fake_search):
    # e.g. Ollama running out of memory mid-answer: the stream just stops
    run = wait_until_done(make_manager(tmp_path, cut_off_roles=("Answer Coach",)).start_prep(build_inputs("Acme", "Analyst", "1-3 years")))
    assert run.status == "completed"
    assert run.warnings == ["The Answer Coach's reply was cut off, so its output is incomplete."]
    assert run.events[-1]["warnings"] == run.warnings
    cut = [e for e in run.events if e["type"] == "llm_completed" and e["cut_off"]]
    assert [e["agent"] for e in cut] == ["coach"]


def test_provider_error_is_reported_not_raised(tmp_path, fake_search):
    class BrokenLLM(ScriptedLLM):
        def call(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

    bridge = EventBridge()
    bridge.install()
    manager = RunManager(bridge, lambda: BrokenLLM(), "fake/broken")
    run = wait_until_done(manager.start_prep(build_inputs("Acme", "Analyst", "1-3 years")))
    assert run.status == "failed"
    assert "model unavailable" in run.error
    assert run.events[-1]["type"] == "run_failed"
