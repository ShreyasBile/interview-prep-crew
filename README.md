# Interview Prep Crew

A multi-agent AI app built with **CrewAI** for interview preparation and resume screening.

- **Interview prep:** enter a company and a role, and four agents research the company, analyse the role, predict the interview questions and coach you on the answers. Add your resume and the questions and answers are built around your own projects and skills.
- **Resume ATS:** upload or paste a resume and get an instant score out of 100 from a rule-based engine, then an AI reviewer agent turns the findings into ranked fixes and bullet rewrites.

The web UI streams every agent's work live: each LLM call, every tool call with its input and output, and each handoff between agents.

```
 Company Researcher ──▶ Role Analyst ──▶ Question Generator ──▶ Answer Coach
  web_search             web_search        (reasoning)            (reasoning)
  news_search            read_webpage
        │                     │                  │                     │
   Company Brief        Role Analysis      10 Likely Questions   Model answers,
                                                                 tips, 5-day plan

 Resume ──▶ rule-based ATS score (instant) ──▶ ATS Resume Reviewer ──▶ ranked fixes + rewrites
```

## The app

| Page | What it does |
|---|---|
| **Dashboard** | Counts of preps and scans, quick actions, recent runs, the ATS score trend (best, average, scans), the crew and system status |
| **Interview prep** | Company, role, experience level, optional job description and resume. Live agent cards with Activity, Prep pack and Sources tabs |
| **Resume ATS** | Upload a PDF, DOCX or TXT (or paste text), optional job description. Score gauge, breakdown by area, matched and missing keywords, then the streamed AI review |
| **History** | Every saved run, with search, a type filter, Markdown download and delete |
| **Agents** | Each agent's role, tools, inputs and outputs, and how the crew is wired |

It has light and dark themes and works on phone-sized screens.

## The agents

| Agent | Tools | Output |
|---|---|---|
| 🏢 Company Researcher | `web_search`, `news_search` (DuckDuckGo, no key needed) | Snapshot, products, culture, recent news with sources, talking points |
| 🧭 Role Analyst | `web_search`, `read_webpage` | Skills, interview rounds, what interviewers look for, gaps to prepare |
| ❓ Question Generator | none | 10 questions (technical, behavioral, company-specific) with "why they ask"; with a resume, at least 3 probe it and are marked **From your resume** |
| 🎓 Answer Coach | none | STAR answer outlines built on your own projects, tips, mistakes to avoid, questions to ask, 5-day plan |
| 📄 ATS Resume Reviewer | none | Prioritised fixes and bullet rewrites, starting from the rule-based score |

The prep crew uses CrewAI's **sequential process**. Each task receives all earlier task outputs as `context`, so later agents build on real research instead of guessing.

### How the ATS score works

The score is computed by deterministic rules (`app/ats.py`), so it is instant, repeatable and needs no model. It covers six areas: **Keyword match** (only when a job description is given), **Sections**, **Contact info**, **Impact** (action verbs and numbers in bullets), **Formatting** and **Language**. Without a job description the keyword area is skipped and the rest is rescaled to 100.

ATS vendors publish no rules and there is no public benchmark, so this is a heuristic, not a prediction of any real ATS. The reviewer agent receives the score as ground truth, may only rewrite bullets that exist in the resume, and writes `[add metric]` instead of inventing a number.

### Resume privacy

The resume is never saved. It is held in the browser page's memory and sent to your own server and to the model you configured, so with Groq or Claude that provider receives it. It is redacted from the task-prompt events before they are shown in the activity feed or written to history. History keeps the company, role, file name, word count, score, report and sources.

## Quick start

Double-click the **Interview Prep Crew** shortcut on the Desktop, or run:

```bat
run.bat
```

The first run creates `.venv`, installs `requirements.txt` and copies `.env.example` to `.env`. The app then opens in your browser at http://127.0.0.1:8010. Close the console window to stop it.

- **Port already in use?** The launcher (`start.py`) moves to the next free port (8011, 8012, …) and says so in the console. To use a different starting port, set `PORT=9000` in `.env`.
- **Already running?** Starting it again just opens the browser on the running copy instead of starting a second server.
- **Shortcut missing?** Recreate it with `powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1`.

**Pick a model in `.env`:**

| Option | Setting | Notes |
|---|---|---|
| Groq | `MODEL=groq/openai/gpt-oss-120b` + `GROQ_API_KEY=...` | Fast, with a free tier (key from console.groq.com); a full run takes about 2 min. Avoid `qwen/qwen3.8-27b` on the free tier: it allows only 1,000 output tokens per minute, which rejects the longer agent answers |
| Claude | `MODEL=anthropic/claude-opus-5-5` + `ANTHROPIC_API_KEY=...` | Best quality |
| Ollama (offline, free) | `MODEL=ollama/interview-prep-qwen3` | Run `scripts\setup_ollama.ps1` once. Uses `qwen3:4b-instruct` (2.5 GB). A full run takes about 6 min on a laptop CPU, faster with a GPU |

The ATS score itself needs no model, so the Resume ATS page still scores a resume when no model is configured; only the AI review is skipped.

## How the live view works

1. `POST /api/runs` (interview prep) or `POST /api/ats` (resume review) starts `crew.kickoff()` in a background thread.
2. `app/events.py` subscribes to **CrewAI's event bus** (`AgentExecutionStarted`, `LLMCallStarted`, `LLMStreamChunk`, `ToolUsageStarted/Finished`, `TaskCompleted`, …) and translates each event into a small JSON event tagged with its agent.
3. `GET /api/runs/{id}/events` streams those events to the browser over **Server-Sent Events** (resumable via `Last-Event-ID`).
4. The `RunViewer` in `static/viewer.js` updates each agent card (status, current action, LLM/tool counters, timer), the activity feed and the report tabs.

## Project layout

```
app/
  config.py    settings from .env, model readiness check, LLM factory (Claude, Groq, Ollama, ...)
  crew.py      the 5 agents, their tasks and the crews
  tools.py     web_search, news_search, read_webpage (CrewAI BaseTool)
  events.py    CrewAI event bus -> UI events, resume redaction
  ats.py       rule-based resume scoring engine
  resume.py    text extraction from PDF, DOCX and TXT
  runs.py      background runs, event log, JSON history store, statistics, Markdown export
  main.py      FastAPI: REST endpoints, SSE stream, report download
static/        frontend (no build step, no external libraries): one script per page, shared
               core.js, components.js and viewer.js, styles.css, app.ico
tests/         155 tests (fake LLM + fake search, fully offline) + an opt-in live test
scripts/       create_shortcut.ps1, setup_ollama.ps1
data/runs/     saved history, one JSON file per run (created at first use, not in git)
start.py       launcher: free-port fallback, reuses a running copy, opens the browser
run.bat        first-time setup + start.py (what the Desktop shortcut runs)
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/config` | model, readiness, agents, tools, experience levels |
| GET | `/api/stats` | counts, ATS score trend, average prep time |
| POST | `/api/resume/parse?filename=` | raw PDF, DOCX or TXT file as the body (up to 5 MB); returns the extracted text |
| POST | `/api/ats` | `{resume, job_description, role, review, filename}`: returns the instant score and starts the AI review |
| POST | `/api/runs` | `{company, role, experience, job_description, resume}` |
| GET | `/api/runs` | recent runs, newest first; `?kind=prep` or `?kind=ats`, `?limit=` |
| GET | `/api/runs/{id}` | status, report and score |
| DELETE | `/api/runs/{id}` | delete a finished run |
| GET | `/api/runs/{id}/events` | SSE stream of agent events |
| GET | `/api/runs/{id}/report.md` | the prep pack or resume report as Markdown |

## Tests

```bat
.venv\Scripts\python.exe -m pytest
```

The suite runs the **real CrewAI crew** end to end, driven by a scripted fake LLM (`tests/fake_llm.py`) and a fake search engine, so it is fast and needs no network. It covers the tools, crew wiring, event translation, the full pipeline, the ATS scoring engine, resume parsing, the HTTP API with SSE, input validation, history and statistics, resume privacy (the resume must never appear in saved history), the Groq/Claude/Ollama model setup, the frontend scripts, and a guard that Claude requests never send `temperature` or a forced `tool_choice` (current Claude models reject both).

`pytest -m live -s` runs the whole crew once against the model configured in `.env`.

## Notes

- Only one AI run at a time: CrewAI's event bus is shared by the whole process. If a prep is running when you scan a resume, you still get the instant score and the AI review is skipped.
- Refreshing the page reconnects to the run in progress.
- Local models: prefer an instruct (non-thinking) model. Thinking models spend minutes per step on a CPU, and CrewAI does not stream their reasoning, so the UI can only show a waiting timer.
- CrewAI telemetry and trace uploads are switched off in `app/config.py`.
- Search results come from DuckDuckGo and can be rate-limited. Agents are told to report "not found" rather than invent facts.
- Your `.env` (API keys) and `data/` (history) stay on your machine and are excluded from git.
