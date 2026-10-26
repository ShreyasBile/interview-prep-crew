"""Turns CrewAI's internal events into small JSON events the frontend can draw.

CrewAI emits an event for everything an agent does (task start, every LLM call,
every streamed token, every tool call, task end). We subscribe once at startup and
forward the translated events to whichever run is live.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable
from urllib.parse import urlsplit

from crewai.events import crewai_event_bus
from crewai.events.types.agent_events import (
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
    AgentExecutionStartedEvent,
)
from crewai.events.types.llm_events import (
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMCallStartedEvent,
    LLMStreamChunkEvent,
    LLMThinkingChunkEvent,
)
from crewai.events.types.task_events import TaskCompletedEvent, TaskFailedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageErrorEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

from app.crew import SPEC_BY_ROLE
from app.tools import parse_results

TOOL_OUTPUT_PREVIEW = 3000
TEXT_PREVIEW = 6000

Sink = Callable[[str, dict[str, Any]], None]


def agent_key(event: Any) -> str | None:
    """Find which of our agents an event belongs to."""
    role = getattr(event, "agent_role", None)
    if not role:
        role = getattr(getattr(event, "agent", None), "role", None)
    if not role:
        output = getattr(event, "output", None)
        role = getattr(output, "agent", None) if not isinstance(output, str) else None
    spec = SPEC_BY_ROLE.get((role or "").strip())
    return spec.key if spec else None


def _text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _tool_args(args: Any) -> dict[str, Any]:
    if isinstance(args, str):  # the ReAct loop reports the raw JSON the model wrote
        try:
            parsed = json.loads(args)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            args = parsed
    if isinstance(args, dict):
        return {k: _text(v, 300) for k, v in args.items()}
    return {"input": _text(args, 300)}


def tool_sources(tool: str, args: dict[str, Any], output: Any) -> list[dict[str, str]]:
    """Web pages a tool call looked at, for the Sources list."""
    if tool == "read_webpage":
        url = str(args.get("url", ""))
        if url.startswith(("http://", "https://")) and not str(output).startswith("Could not read"):
            return [{"title": urlsplit(url).netloc or url, "url": url}]
        return []
    return parse_results(str(output))


def is_cut_off(event: LLMCallCompletedEvent) -> bool:
    """True when a text reply did not finish normally.

    Either it hit the length limit, or the stream simply stopped: no finish reason and
    no usage numbers, which is what a crashed local model (e.g. Ollama out of memory)
    looks like. CrewAI would otherwise accept the half-written text as the answer.
    """
    if not isinstance(event.response, str):
        return False
    if event.finish_reason in ("length", "max_tokens"):
        return True
    return event.finish_reason is None and not event.usage


def redact(text: str, secrets: dict[str, str] | None) -> str:
    """Replace private inputs (the resume) so they never reach the UI or the saved history."""
    for name, secret in (secrets or {}).items():
        if secret and secret in text:
            text = text.replace(secret, f"[{name} hidden: {len(secret.split())} words]")
    return text


def translate(event: Any, secrets: dict[str, str] | None = None) -> tuple[str, dict[str, Any]] | None:
    """Map one CrewAI event to (ui_event_type, payload). None = not shown in the UI."""
    agent = agent_key(event)
    if agent is None:
        return None

    if isinstance(event, AgentExecutionStartedEvent):
        # redact first: truncating could otherwise cut a secret in half and defeat the match
        prompt = _text(redact(event.task_prompt, secrets), TEXT_PREVIEW)
        return "agent_started", {"agent": agent, "task_prompt": prompt}
    if isinstance(event, AgentExecutionCompletedEvent):
        return "agent_completed", {"agent": agent}
    if isinstance(event, AgentExecutionErrorEvent):
        return "agent_error", {"agent": agent, "error": _text(event.error, 800)}

    if isinstance(event, LLMCallStartedEvent):
        return "llm_started", {"agent": agent, "call_id": event.call_id, "model": event.model}
    if isinstance(event, LLMStreamChunkEvent):
        if event.tool_call is not None or not event.chunk:
            return None  # tool-call argument fragments; the tool event shows them better
        return "llm_chunk", {"agent": agent, "call_id": event.call_id, "text": event.chunk}
    if isinstance(event, LLMThinkingChunkEvent):
        if not event.chunk:
            return None
        return "llm_thinking", {"agent": agent, "call_id": event.call_id, "text": event.chunk}
    if isinstance(event, LLMCallCompletedEvent):
        response = event.response if isinstance(event.response, str) else ""
        return "llm_completed", {
            "agent": agent,
            "call_id": event.call_id,
            "text": _text(response, TEXT_PREVIEW),
            "wants_tool": not isinstance(event.response, str),
            "usage": event.usage or {},
            "finish_reason": event.finish_reason,
            "cut_off": is_cut_off(event),
        }
    if isinstance(event, LLMCallFailedEvent):
        return "llm_failed", {"agent": agent, "call_id": event.call_id, "error": _text(event.error, 800)}

    if isinstance(event, ToolUsageStartedEvent):
        return "tool_started", {"agent": agent, "tool": event.tool_name, "args": _tool_args(event.tool_args)}
    if isinstance(event, ToolUsageFinishedEvent):
        args = _tool_args(event.tool_args)
        return "tool_finished", {
            "agent": agent,
            "tool": event.tool_name,
            "args": args,
            "output": _text(event.output, TOOL_OUTPUT_PREVIEW),
            "sources": tool_sources(event.tool_name, args, event.output),
            "from_cache": event.from_cache,
        }
    if isinstance(event, ToolUsageErrorEvent):
        return "tool_error", {"agent": agent, "tool": event.tool_name, "error": _text(event.error, 800)}

    if isinstance(event, TaskCompletedEvent):
        return "task_completed", {"agent": agent, "output": event.output.raw}
    if isinstance(event, TaskFailedEvent):
        return "task_failed", {"agent": agent, "error": _text(event.error, 800)}
    return None


WATCHED_EVENTS = (
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
    LLMCallStartedEvent,
    LLMStreamChunkEvent,
    LLMThinkingChunkEvent,
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    ToolUsageStartedEvent,
    ToolUsageFinishedEvent,
    ToolUsageErrorEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
)


class EventBridge:
    """Subscribes to the CrewAI event bus once and forwards events to the live run."""

    def __init__(self) -> None:
        self._sink: Sink | None = None
        self._secrets: dict[str, str] = {}
        self._lock = threading.Lock()
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        # Async handlers all run on CrewAI's single event loop, so they keep emission order
        # (sync handlers are spread over a thread pool and can arrive out of order).
        for event_type in WATCHED_EVENTS:
            crewai_event_bus.on(event_type)(self._handle)
        self._installed = True

    async def _handle(self, source: Any, event: Any) -> None:
        self.forward(event)

    def forward(self, event: Any) -> None:
        with self._lock:
            sink, secrets = self._sink, self._secrets
        if sink is None:
            return
        translated = translate(event, secrets)
        if translated is not None:
            sink(*translated)

    def attach(self, sink: Sink, secrets: dict[str, str] | None = None) -> None:
        with self._lock:
            self._sink = sink
            self._secrets = dict(secrets or {})

    def detach(self) -> None:
        with self._lock:
            self._sink = None
            self._secrets = {}


bridge = EventBridge()
