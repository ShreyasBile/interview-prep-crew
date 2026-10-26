"""A scripted stand-in for a real model, so the whole crew runs offline in tests.

It speaks CrewAI's ReAct text format: research agents first ask for one tool, then
give a final answer; the other agents answer straight away. It emits the same
LLM events (started / streamed chunks / completed) as a real provider.
"""

from __future__ import annotations

import time
from typing import Any

from crewai.events.types.llm_events import LLMCallType
from crewai.llms.base_llm import BaseLLM, llm_call_context
from pydantic import PrivateAttr

FINAL_ANSWERS = {
    "Company Researcher": "## Snapshot\n- Acme Corp builds analytics software.\n## Recent News\n- Launched Acme Cloud (acme.example)",
    "Role Analyst": "## Role Summary\nData analysts turn data into decisions.\n## Must-Have Skills\n- SQL\n- Python",
    "Question Generator": "## Technical / Role Questions\n1. **How would you clean a messy dataset?**\n*Why they ask:* core skill.",
    "Answer Coach": "## Answer Guide\n### Q1\n**Model answer:**\n- Profile, clean, validate\n**Tip:** be concrete\n**Avoid:** jargon",
    "ATS Resume Reviewer": "## Verdict\nSolid base.\n## Top Fixes\n1. Add metrics to your bullets.",
}

PROMPTS_SEEN: list[tuple[str, str]] = []  # (agent role, everything the model was sent), for tests

TOOL_CALLS = {
    "Company Researcher": ("web_search", '{"query": "Acme Corp culture"}'),
    "Role Analyst": ("web_search", '{"query": "Acme Corp data analyst interview"}'),
}


class ScriptedLLM(BaseLLM):
    model: str = "fake/scripted"
    delay: float = 0.0  # seconds per call, to keep a run busy in tests
    cut_off_roles: tuple[str, ...] = ()  # roles whose replies end like a crashed stream
    _calls_per_role: dict[str, int] = PrivateAttr(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        data.setdefault("model", "fake/scripted")  # BaseLLM validates model before defaults apply
        super().__init__(**data)

    def supports_function_calling(self) -> bool:
        return False  # use the ReAct text loop

    def call(
        self,
        messages: Any,
        tools: Any = None,
        callbacks: Any = None,
        available_functions: Any = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        with llm_call_context():
            self._emit_call_started_event(
                messages=messages, tools=tools, callbacks=callbacks,
                available_functions=available_functions, from_task=from_task, from_agent=from_agent,
            )
            role = from_agent.role if from_agent is not None else ""
            PROMPTS_SEEN.append((role, str(messages)))
            n = self._calls_per_role.get(role, 0)
            self._calls_per_role[role] = n + 1
            reply = self._reply(role, n)
            if self.delay:
                time.sleep(self.delay)
            for start in range(0, len(reply), 20):
                self._emit_stream_chunk_event(reply[start : start + 20], from_task=from_task, from_agent=from_agent)
            finished = role not in self.cut_off_roles
            self._emit_call_completed_event(
                response=reply, call_type=LLMCallType.LLM_CALL,
                from_task=from_task, from_agent=from_agent, messages=messages,
                finish_reason="stop" if finished else None,
                usage={"prompt_tokens": 100, "completion_tokens": len(reply) // 4} if finished else None,
            )
            return reply

    @staticmethod
    def _reply(role: str, n: int) -> str:
        if role in TOOL_CALLS and n == 0:
            tool, args = TOOL_CALLS[role]
            return f"Thought: I should look this up.\nAction: {tool}\nAction Input: {args}"
        return f"Thought: I now know the final answer\nFinal Answer: {FINAL_ANSWERS.get(role, 'Done.')}"
