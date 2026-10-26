# Interview Prep Crew

A multi-agent AI app built with **CrewAI**. Enter a company and a role, and four agents research the company, analyse the role, predict the interview questions and coach you on the answers. The web UI streams every agent's work live: each LLM call, every tool call with its input and output, and each handoff between agents.

```
 Company Researcher ──▶ Role Analyst ──▶ Question Generator ──▶ Answer Coach
  web_search             web_search        (reasoning)            (reasoning)
  news_search            read_webpage
        │                     │                  │                     │
   Company Brief        Role Analysis      10 Likely Questions   Model answers,
                                                                 tips, 5-day plan
```

| Agent | Tools | Output |
|---|---|---|
| 🏢 Company Researcher | `web_search`, `news_search` (DuckDuckGo, no key needed) | Snapshot, products, culture, recent news with sources, talking points |
| 🧭 Role Analyst | `web_search`, `read_webpage` | Skills, interview rounds, what interviewers look for, gaps to prepare |
| ❓ Question Generator | none | 10 questions (technical, behavioral, company-specific) with "why they ask" |
| 🎓 Answer Coach | none | STAR answer outlines, tips, mistakes to avoid, questions to ask, 5-day plan |

The crew uses CrewAI's **sequential process**. Each task receives all earlier task outputs as `context`, so later agents build on real research instead of guessing.

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

## How the live view works

1. `POST /api/runs` starts `crew.kickoff()` in a background thread.
2. `app/events.py` subscribes to **CrewAI's event bus** (`AgentExecutionStarted`, `LLMCallStarted`, `LLMStreamChunk`, `ToolUsageStarted/Finished`, `TaskCompleted`, …) and translates each event into a small JSON event tagged with its agent.
3. `GET /api/runs/{id}/events` streams those events to the browser over **Server-Sent Events** (resumable via `Last-Event-ID`).
4. `static/app.js` updates each agent card (status, current action, LLM/tool counters, timer), the activity feed and the report tabs.

## Project layout

```
app/
  config.py    settings from .env, model readiness check, LLM factory (Claude, Groq, Ollama, ...)
  crew.py      the 4 agents, their tasks and the crew
  tools.py     web_search, news_search, read_webpage (CrewAI BaseTool)
  events.py    CrewAI event bus -> UI events
  runs.py      background runs, event log, Markdown export
  main.py      FastAPI: /api/config, /api/runs, SSE stream, report download
static/        frontend (no build step, no external libraries) and app.ico
tests/         79 tests (fake LLM + fake search, fully offline) + an opt-in live test
scripts/       create_shortcut.ps1, setup_ollama.ps1
start.py       launcher: free-port fallback, reuses a running copy, opens the browser
run.bat        first-time setup + start.py (what the Desktop shortcut runs)
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/config` | model, readiness, agents |
| GET | `/api/runs` | recent runs, newest first |
| POST | `/api/runs` | `{company, role, experience, job_description}` |
| GET | `/api/runs/{id}` | status and report |
| GET | `/api/runs/{id}/events` | SSE stream of agent events |
| GET | `/api/runs/{id}/report.md` | the prep pack as Markdown |

## Tests

```bat
.venv\Scripts\python.exe -m pytest
```

The suite runs the **real CrewAI crew** end to end, driven by a scripted fake LLM (`tests/fake_llm.py`) and a fake search engine, so it is fast and needs no network. It covers the tools, crew wiring, event translation, the full pipeline, the HTTP API with SSE, input validation, the Groq/Claude/Ollama model setup, and a guard that Claude requests never send `temperature` or a forced `tool_choice` (current Claude models reject both).

`pytest -m live -s` runs the whole crew once against the model configured in `.env`.

## Notes

- Only one run at a time: CrewAI's event bus is shared by the whole process.
- Refreshing the page reconnects to the run in progress (the run id is kept in the URL).
- Local models: prefer an instruct (non-thinking) model. Thinking models spend minutes per step on a CPU, and CrewAI does not stream their reasoning, so the UI can only show a waiting timer.
- CrewAI telemetry and trace uploads are switched off in `app/config.py`.
- Search results come from DuckDuckGo and can be rate-limited. Agents are told to report "not found" rather than invent facts.
