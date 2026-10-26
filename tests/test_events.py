import pytest
from crewai.events.types.llm_events import LLMCallCompletedEvent, LLMCallType, LLMStreamChunkEvent, ToolCall, FunctionCall
from crewai.events.types.task_events import TaskCompletedEvent
from crewai.events.types.tool_usage_events import ToolUsageFinishedEvent, ToolUsageStartedEvent
from crewai.tasks.task_output import TaskOutput

from app.events import EventBridge, translate
from app.runs import Run, coalesce


def test_tool_start_is_mapped_to_the_right_agent():
    ev = ToolUsageStartedEvent(tool_name="web_search", tool_args={"query": "Acme culture"}, agent_role="Company Researcher")
    assert translate(ev) == ("tool_started", {"agent": "researcher", "tool": "web_search", "args": {"query": "Acme culture"}})


def test_tool_args_given_as_json_text_are_parsed():
    ev = ToolUsageStartedEvent(tool_name="read_webpage", tool_args='{"url": "https://a.example"}', agent_role="Role Analyst")
    assert translate(ev)[1]["args"] == {"url": "https://a.example"}


def test_tool_output_is_truncated():
    from datetime import datetime

    ev = ToolUsageFinishedEvent(
        tool_name="web_search", tool_args={}, agent_role="Role Analyst",
        started_at=datetime.now(), finished_at=datetime.now(), output="x" * 5000,
    )
    kind, payload = translate(ev)
    assert kind == "tool_finished" and payload["agent"] == "analyst"
    assert len(payload["output"]) == 3001


def test_events_from_unknown_agents_are_ignored():
    ev = ToolUsageStartedEvent(tool_name="web_search", tool_args={}, agent_role="Someone Else")
    assert translate(ev) is None


def test_text_chunks_are_forwarded_but_tool_call_fragments_are_not():
    text = LLMStreamChunkEvent(chunk="Hello", call_id="c1", agent_role="Answer Coach")
    assert translate(text) == ("llm_chunk", {"agent": "coach", "call_id": "c1", "text": "Hello"})
    fragment = LLMStreamChunkEvent(
        chunk='{"qu', call_id="c1", agent_role="Answer Coach",
        tool_call=ToolCall(function=FunctionCall(arguments='{"qu'), index=0),
    )
    assert translate(fragment) is None


@pytest.mark.parametrize(
    "response, finish_reason, usage, cut",
    [
        ("Full answer", "stop", {"total_tokens": 9}, False),
        ("Full answer", "end_turn", None, False),  # Claude reports its own stop reasons
        ("Half an ans", "length", {"total_tokens": 9}, True),
        ("Half an ans", "max_tokens", None, True),
        ("Half an ans", None, None, True),  # stream just stopped (crashed local model)
        ([{"id": "call"}], None, None, False),  # tool requests are never "cut off"
    ],
)
def test_cut_off_replies_are_detected(response, finish_reason, usage, cut):
    ev = LLMCallCompletedEvent(
        call_id="c", response=response, call_type=LLMCallType.LLM_CALL,
        agent_role="Answer Coach", finish_reason=finish_reason, usage=usage,
    )
    assert translate(ev)[1]["cut_off"] is cut


def test_llm_completed_flags_tool_requests():
    text = LLMCallCompletedEvent(call_id="c", response="Final", call_type=LLMCallType.LLM_CALL, agent_role="Role Analyst")
    assert translate(text)[1]["wants_tool"] is False
    tool = LLMCallCompletedEvent(call_id="c", response=[{"id": "1"}], call_type=LLMCallType.TOOL_CALL, agent_role="Role Analyst")
    assert translate(tool)[1]["wants_tool"] is True


def test_task_completed_uses_output_agent_when_role_missing():
    output = TaskOutput(description="d", raw="## Answer Guide", agent="Answer Coach")
    ev = TaskCompletedEvent(output=output)
    assert translate(ev) == ("task_completed", {"agent": "coach", "output": "## Answer Guide"})


def test_bridge_only_forwards_while_a_sink_is_attached():
    bridge = EventBridge()
    got = []
    ev = ToolUsageStartedEvent(tool_name="web_search", tool_args={}, agent_role="Company Researcher")
    bridge.forward(ev)
    bridge.attach(lambda kind, payload: got.append(kind))
    bridge.forward(ev)
    bridge.detach()
    bridge.forward(ev)
    assert got == ["tool_started"]


def test_coalesce_merges_only_consecutive_chunks_of_one_call():
    events = [
        {"seq": 1, "type": "llm_chunk", "call_id": "a", "text": "Hel"},
        {"seq": 2, "type": "llm_chunk", "call_id": "a", "text": "lo"},
        {"seq": 3, "type": "llm_chunk", "call_id": "b", "text": "Hi"},
        {"seq": 4, "type": "tool_started", "tool": "web_search"},
        {"seq": 5, "type": "llm_chunk", "call_id": "b", "text": "!"},
    ]
    merged = coalesce(events)
    assert [(e["seq"], e.get("text")) for e in merged] == [(2, "Hello"), (3, "Hi"), (4, None), (5, "!")]
    assert events[0]["text"] == "Hel"  # input is not modified


def test_run_collects_report_and_builds_markdown():
    run = Run(id="r1", inputs={"company": "Acme", "role": "Analyst", "experience": "1-3 years"}, model="m")
    run.add("task_completed", {"agent": "researcher", "output": "## Snapshot\n- Acme"})
    run.finish()
    assert run.report == {"researcher": "## Snapshot\n- Acme"}
    assert run.events[-1]["type"] == "run_completed"
    md = run.to_markdown()
    assert md.startswith("# Interview Prep: Analyst at Acme")
    assert "Company Brief" in md and "Role Analysis" not in md
