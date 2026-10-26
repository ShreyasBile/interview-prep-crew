"""FastAPI server: serves the frontend and streams agent events over SSE.

Run with:  python -m uvicorn app.main:app --port 8010   (or use start.py)
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.config import DATA_DIR, STATIC_DIR, Settings, get_settings, make_llm  # config first: sets env flags
from app.ats import analyze, summarize
from app.crew import build_ats_inputs, build_inputs, tool_info
from app.events import bridge
from app.resume import MAX_BYTES, MAX_CHARS, ResumeError, extract_text
from app.runs import KINDS, RunBusyError, RunManager, RunStore, agents_payload, coalesce

EXPERIENCE_LEVELS = ("Fresher / intern", "1-3 years", "3-6 years", "6+ years")


class RunRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=80)
    role: str = Field(..., min_length=1, max_length=80)
    experience: Literal[EXPERIENCE_LEVELS] = "1-3 years"  # type: ignore[valid-type]
    job_description: str = Field("", max_length=4000)
    resume: str = Field("", max_length=MAX_CHARS)


class AtsRequest(BaseModel):
    resume: str = Field(..., min_length=1, max_length=MAX_CHARS)
    job_description: str = Field("", max_length=6000)
    role: str = Field("", max_length=80)
    filename: str = Field("", max_length=120)
    review: bool = True  # also run the AI reviewer agent


def create_app(settings: Settings | None = None, manager: RunManager | None = None) -> FastAPI:
    settings = settings or get_settings()
    if manager is None:
        bridge.install()
        manager = RunManager(bridge, lambda: make_llm(settings), settings.model, RunStore(DATA_DIR / "runs"))

    app = FastAPI(title="Interview Prep Crew", version=__version__)
    app.state.manager = manager
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/config")
    def config() -> dict:
        ready, reason = settings.live_status()
        return {
            "version": __version__,
            "model": settings.model,
            "provider": settings.provider,
            "live_ready": ready,
            "live_reason": reason,
            "agents": agents_payload(),
            "tools": tool_info(),
            "experience_levels": list(EXPERIENCE_LEVELS),
            "saved_runs": len(manager.runs),
        }

    @app.get("/api/stats")
    def stats() -> dict:
        return manager.stats()

    # ----- resume helpers -----

    @app.post("/api/resume/parse")
    async def parse_resume(request: Request, filename: str = Query("resume.txt", max_length=200)) -> dict:
        """Extract plain text from an uploaded resume (the raw file is the request body)."""
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES + 4096:
            raise HTTPException(413, "The file is larger than 5 MB.")
        data = await request.body()
        try:
            text = await asyncio.to_thread(extract_text, filename, data)
        except ResumeError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"text": text, "words": len(text.split()), "chars": len(text), "filename": filename}

    @app.post("/api/ats", status_code=201)
    def scan_resume(req: AtsRequest) -> dict:
        try:
            score = analyze(req.resume, req.job_description)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        review, skipped = req.review, None
        if review:
            ready, reason = settings.live_status()
            if not ready:
                review, skipped = False, reason
        inputs = build_ats_inputs(req.resume, req.job_description, req.role, summarize(score))
        run, busy = manager.start_ats(inputs, score, review, req.filename)
        return {**run.summary(), "review_skipped": skipped or busy}

    # ----- interview prep and runs -----

    @app.post("/api/runs", status_code=201)
    def start_run(req: RunRequest) -> dict:
        if not req.company.strip() or not req.role.strip():
            raise HTTPException(422, "Company and role are required.")
        ready, reason = settings.live_status()
        if not ready:
            raise HTTPException(400, reason)
        try:
            run = manager.start_prep(
                build_inputs(req.company, req.role, req.experience, req.job_description, req.resume)
            )
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        return run.summary()

    @app.get("/api/runs")
    def list_runs(kind: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
        """Newest first, without reports (used for history and to re-attach after a reload)."""
        if kind is not None and kind not in KINDS:
            raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
        return [run.brief() for run in manager.list(kind, limit)]

    def _get_run(run_id: str):
        run = manager.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/runs/{run_id}")
    def run_summary(run_id: str) -> dict:
        return _get_run(run_id).summary()

    @app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(run_id: str) -> Response:
        _get_run(run_id)
        try:
            manager.delete(run_id)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request) -> StreamingResponse:
        run = _get_run(run_id)
        last_id = request.headers.get("last-event-id") or request.query_params.get("after") or "0"
        cursor = int(last_id) if last_id.isdigit() else 0

        async def stream():
            nonlocal cursor
            idle = 0.0
            while True:
                new = run.events_after(cursor)
                if new:
                    cursor += len(new)
                    idle = 0.0
                    for ev in coalesce(new):
                        yield f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    continue
                if run.done:
                    break
                if await request.is_disconnected():
                    break
                await asyncio.sleep(0.15)
                idle += 0.15
                if idle >= 15:  # keep proxies from closing a quiet connection
                    idle = 0.0
                    yield ": keep-alive\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/runs/{run_id}/report.md")
    def run_report(run_id: str) -> PlainTextResponse:
        run = _get_run(run_id)
        slug = re.sub(r"[^a-z0-9]+", "-", run.title().lower()).strip("-")[:60]
        prefix = "resume-report" if run.kind == "ats" else "interview-prep"
        return PlainTextResponse(
            run.to_markdown(),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{prefix}-{slug or "report"}.md"'},
        )

    return app


app = create_app()
