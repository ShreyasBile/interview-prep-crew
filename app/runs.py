"""Runs (interview preps and resume scans): background execution, event log and history."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from crewai.events import crewai_event_bus

from app.crew import ALL_SPECS, NOT_PROVIDED, SPECS_BY_KIND, build_crew
from app.events import EventBridge

RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
KINDS = ("prep", "ats")
MAX_SOURCES = 60


class RunBusyError(RuntimeError):
    """Only one crew runs at a time: CrewAI's event bus is shared by the whole process."""


def agents_payload(kind: str | None = None) -> list[dict[str, Any]]:
    specs = ALL_SPECS if kind is None else SPECS_BY_KIND[kind]
    return [
        {
            "key": s.key,
            "role": s.role,
            "icon": s.icon,
            "summary": s.summary,
            "tools": list(s.tools),
            "report_title": s.report_title,
            "kind": s.kind,
            "reads": s.reads,
            "produces": s.produces,
        }
        for s in specs
    ]


def coalesce(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge runs of streamed text chunks from the same LLM call into one event."""
    merged: list[dict[str, Any]] = []
    for ev in events:
        last = merged[-1] if merged else None
        if (
            last is not None
            and ev["type"] in ("llm_chunk", "llm_thinking")
            and last["type"] == ev["type"]
            and last.get("call_id") == ev.get("call_id")
        ):
            last["text"] += ev["text"]
            last["seq"] = ev["seq"]
            continue
        merged.append(dict(ev))
    return merged


@dataclass
class Run:
    id: str
    inputs: dict[str, Any]  # public inputs only: the resume text is never stored
    model: str
    kind: str = "prep"
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    score: dict[str, Any] | None = None  # ATS analysis (kind == "ats")
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            event = {"seq": len(self.events) + 1, "ts": round(time.time(), 3), "type": type_, **(payload or {})}
            self.events.append(event)
        if type_ == "task_completed":
            self.report[event["agent"]] = event["output"]
        elif type_ == "llm_completed" and event.get("cut_off"):
            role = next(s.role for s in ALL_SPECS if s.key == event["agent"])
            self.warnings.append(f"The {role}'s reply was cut off, so its output is incomplete.")
        elif type_ == "tool_finished":
            self._add_sources(event)
        return event

    def _add_sources(self, event: dict[str, Any]) -> None:
        known = {s["url"] for s in self.sources}
        for source in event.get("sources", []):
            if source["url"] not in known and len(self.sources) < MAX_SOURCES:
                known.add(source["url"])
                self.sources.append({**source, "agent": event["agent"], "tool": event["tool"]})

    def events_after(self, seq: int) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.events[seq:])

    @property
    def done(self) -> bool:
        return self.status != "running"

    @property
    def duration(self) -> float:
        return round((self.finished_at or time.time()) - self.started_at, 1)

    def finish(self) -> None:
        self.finished_at = time.time()
        self.status = "completed"
        self.add(
            "run_completed",
            {"duration": self.duration, "report": self.report, "warnings": self.warnings, "sources": self.sources},
        )

    def fail(self, error: str) -> None:
        self.finished_at = time.time()
        self.error = error
        self.status = "failed"
        self.add("run_failed", {"error": error})

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "inputs": self.inputs,
            "model": self.model,
            "report": self.report,
            "warnings": self.warnings,
            "sources": self.sources,
            "score": self.score,
            "error": self.error,
            "event_count": len(self.events),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
        }

    def brief(self) -> dict[str, Any]:
        """The summary without the bulky parts, for lists."""
        data = self.summary()
        for key in ("report", "sources"):
            data.pop(key)
        if self.score:
            data["score"] = {"score": self.score["score"], "grade": self.score["grade"]}
        data["sources"] = len(self.sources)
        return data

    def to_record(self) -> dict[str, Any]:
        return {**self.summary(), "events": coalesce(self.events)}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Run":
        events = record.get("events", [])
        for i, ev in enumerate(events, 1):  # merging chunks left gaps; seq must equal list position + 1
            ev["seq"] = i
        return cls(
            id=record["id"],
            inputs=record["inputs"],
            model=record["model"],
            kind=record.get("kind", "prep"),
            status=record["status"],
            events=events,
            report=record.get("report", {}),
            warnings=record.get("warnings", []),
            sources=record.get("sources", []),
            score=record.get("score"),
            error=record.get("error"),
            started_at=record["started_at"],
            finished_at=record.get("finished_at"),
        )

    def title(self) -> str:
        if self.kind == "ats":
            return f"Resume scan: {self.inputs.get('filename') or self.inputs.get('role') or 'pasted resume'}"
        return f"{self.inputs.get('role')} at {self.inputs.get('company')}"

    def to_markdown(self) -> str:
        return self._ats_markdown() if self.kind == "ats" else self._prep_markdown()

    def _prep_markdown(self) -> str:
        info = f"Experience level: {self.inputs.get('experience')} · Generated by 4 CrewAI agents ({self.model})"
        if self.inputs.get("has_resume"):
            info += " · Personalised with the candidate's resume"
        lines = [f"# Interview Prep: {self.title()}", "", f"*{info}*"]
        for spec in SPECS_BY_KIND["prep"]:
            if spec.key in self.report:
                lines += ["", f"# {spec.icon} {spec.report_title}", f"*by the {spec.role}*", "", self.report[spec.key].strip()]
        if self.sources:
            lines += ["", "# Sources", ""] + [f"- [{s['title']}]({s['url']})" for s in self.sources]
        return "\n".join(lines) + "\n"

    def _ats_markdown(self) -> str:
        score = self.score or {}
        role = self.inputs.get("role") or "general applications"
        lines = [
            "# Resume ATS Report",
            "",
            f"*Target: {role} · ATS score {score.get('score')}/100 ({score.get('grade')})*",
            "",
            "## Score breakdown",
            "",
            "| Area | Score |",
            "|---|---|",
        ]
        marks = {"pass": "✔", "warn": "⚠", "fail": "✖"}
        for area in score.get("areas", []):
            lines.append(f"| {area['label']} | {area['score']} / {area['max']} |")
        for area in score.get("areas", []):
            lines += ["", f"### {area['label']}"]
            for c in area["checks"]:
                lines.append(f"- {marks[c['status']]} {c['title']}" + (f": {c['detail']}" if c["detail"] else ""))
        keywords = score.get("keywords", {})
        if keywords.get("matched") or keywords.get("missing"):
            lines += ["", "## Keywords", f"- Found: {', '.join(keywords['matched']) or 'none'}", f"- Missing: {', '.join(keywords['missing']) or 'none'}"]
        if "ats_reviewer" in self.report:
            lines += ["", "# AI Review", "", self.report["ats_reviewer"].strip()]
        return "\n".join(lines) + "\n"


class RunStore:
    """One JSON file per finished run, so history survives restarts."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, run_id: str) -> Path:
        if not RUN_ID_RE.match(run_id):
            raise ValueError(f"invalid run id: {run_id!r}")
        return self.directory / f"{run_id}.json"

    def save(self, run: Run) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(run.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(run.to_record(), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def load_all(self) -> list[Run]:
        runs = []
        for path in sorted(self.directory.glob("*.json")) if self.directory.exists() else []:
            try:
                runs.append(Run.from_record(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue  # a damaged file should not stop the app from starting
        return runs

    def delete(self, run_id: str) -> None:
        self._path(run_id).unlink(missing_ok=True)


class RunManager:
    def __init__(
        self,
        bridge: EventBridge,
        llm_factory: Callable[[], Any],
        model_label: str,
        store: RunStore | None = None,
    ) -> None:
        self.bridge = bridge
        self.llm_factory = llm_factory
        self.model_label = model_label
        self.store = store
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._current: Run | None = None
        if store is not None:
            for run in store.load_all():
                self.runs[run.id] = run

    # ----- queries -----

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def list(self, kind: str | None = None, limit: int = 100) -> list[Run]:
        runs = [r for r in self.runs.values() if kind in (None, r.kind)]
        return sorted(runs, key=lambda r: r.started_at, reverse=True)[:limit]

    def delete(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run is None:
            return False
        if not run.done:
            raise RunBusyError("This run is still in progress.")
        del self.runs[run_id]
        if self.store is not None:
            self.store.delete(run_id)
        return True

    def stats(self) -> dict[str, Any]:
        runs = list(self.runs.values())
        preps = [r for r in runs if r.kind == "prep" and r.status == "completed"]
        scans = sorted((r for r in runs if r.kind == "ats" and r.score), key=lambda r: r.started_at)
        scores = [r.score["score"] for r in scans]
        steps = tool_calls = 0
        for run in runs:
            for ev in run.events_after(0):
                if ev["type"] == "llm_started":
                    steps += 1
                elif ev["type"] == "tool_started":
                    steps += 1
                    tool_calls += 1
        return {
            "preps": len(preps),
            "scans": len(scans),
            "avg_score": round(sum(scores) / len(scores)) if scores else None,
            "best_score": max(scores) if scores else None,
            "score_trend": [{"id": r.id, "score": r.score["score"], "at": r.started_at} for r in scans[-12:]],
            "agent_steps": steps,
            "tool_calls": tool_calls,
            "sources": sum(len(r.sources) for r in runs),
            "avg_prep_seconds": round(sum(r.duration for r in preps) / len(preps)) if preps else None,
        }

    # ----- starting runs -----

    def start_prep(self, inputs: dict[str, str]) -> Run:
        public = {
            "company": inputs["company"],
            "role": inputs["role"],
            "experience": inputs["experience"],
            "has_job_description": inputs["job_description"] != NOT_PROVIDED,
            "has_resume": inputs["resume"] != NOT_PROVIDED,
            "resume_words": 0 if inputs["resume"] == NOT_PROVIDED else len(inputs["resume"].split()),
        }
        return self._start_crew("prep", public, inputs)

    def start_ats(
        self, inputs: dict[str, str], score: dict[str, Any], review: bool, filename: str = ""
    ) -> tuple[Run, str | None]:
        """Start a resume scan. Returns (run, reason the AI review was skipped or None)."""
        public = {
            "role": inputs["role"],
            "filename": filename,
            "has_job_description": inputs["job_description"] != NOT_PROVIDED,
            "resume_words": len(inputs["resume"].split()),
        }
        skipped = None
        if review:
            try:
                return self._start_crew("ats", public, inputs, score=score), None
            except RunBusyError as exc:
                skipped = str(exc)
        run = Run(id=uuid.uuid4().hex[:12], inputs=public, model=self.model_label, kind="ats", score=score)
        self.runs[run.id] = run
        run.add("run_started", self._started_payload(run, agents=[]))
        run.finish()
        self._persist(run)
        return run, skipped

    def _start_crew(self, kind: str, public: dict[str, Any], crew_inputs: dict[str, str], score: dict | None = None) -> Run:
        with self._lock:
            if self._current is not None and not self._current.done:
                raise RunBusyError("An AI run is already in progress. Wait for it to finish.")
            run = Run(id=uuid.uuid4().hex[:12], inputs=public, model=self.model_label, kind=kind, score=score)
            self.runs[run.id] = run
            self._current = run
        threading.Thread(target=self._execute, args=(run, crew_inputs), daemon=True, name=f"run-{run.id}").start()
        return run

    @staticmethod
    def _started_payload(run: Run, agents: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "kind": run.kind,
            "inputs": run.inputs,
            "model": run.model,
            "agents": agents,
            "score": run.score,
            "review": bool(agents),
        }

    def _execute(self, run: Run, crew_inputs: dict[str, str]) -> None:
        resume = crew_inputs.get("resume", NOT_PROVIDED)
        self.bridge.attach(run.add, secrets={} if resume == NOT_PROVIDED else {"resume": resume})
        try:
            run.add("run_started", self._started_payload(run, agents_payload(run.kind)))
            crew = build_crew(self.llm_factory(), run.kind)
            crew.kickoff(inputs=crew_inputs)
            crewai_event_bus.flush()  # deliver every queued agent event before "completed"
            missing = [s.role for s in SPECS_BY_KIND[run.kind] if s.key not in run.report]
            if missing:
                run.fail(f"The crew finished without output from: {', '.join(missing)}")
            else:
                run.finish()
        except Exception as exc:  # surface any model/provider error in the UI
            crewai_event_bus.flush()
            run.fail(f"{type(exc).__name__}: {exc}")
        finally:
            self.bridge.detach()
            self._persist(run)

    def _persist(self, run: Run) -> None:
        if self.store is None:
            return
        try:
            self.store.save(run)
        except OSError:
            pass  # history is a convenience; never fail a run because the disk is read-only
