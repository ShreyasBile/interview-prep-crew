import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.events import EventBridge
from app.main import create_app
from app.runs import RunManager, RunStore
from tests.conftest import wait_until_done
from tests.fake_llm import ScriptedLLM

FAKE_SETTINGS = Settings(model="fake/scripted", max_tokens=1000, ollama_host="http://localhost:11434")
GOOD_RUN = {"company": "Acme Corp", "role": "Data Analyst", "experience": "1-3 years", "job_description": ""}


def make_client(tmp_path, delay=0.0, settings=FAKE_SETTINGS, store=False):
    bridge = EventBridge()
    bridge.install()
    run_store = RunStore(tmp_path / "runs") if store else None
    manager = RunManager(bridge, lambda: ScriptedLLM(delay=delay), settings.model, run_store)
    return TestClient(create_app(settings=settings, manager=manager)), manager


def read_sse(client, run_id):
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_frontend_is_served(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200 and "Interview Prep Crew" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.ico").status_code == 200


def test_config_describes_the_agents(tmp_path):
    client, _ = make_client(tmp_path)
    cfg = client.get("/api/config").json()
    assert cfg["live_ready"] is True
    prep = [a for a in cfg["agents"] if a["kind"] == "prep"]
    assert [a["role"] for a in prep] == ["Company Researcher", "Role Analyst", "Question Generator", "Answer Coach"]
    assert prep[0]["tools"] == ["web_search", "news_search"]
    assert [a["role"] for a in cfg["agents"] if a["kind"] == "ats"] == ["ATS Resume Reviewer"]
    assert {t["name"] for t in cfg["tools"]} == {"web_search", "news_search", "read_webpage"}
    assert all(a["reads"] and a["produces"] for a in cfg["agents"])


@pytest.mark.parametrize(
    "change",
    [{"company": ""}, {"role": ""}, {"company": "x" * 81}, {"experience": "10 years"}, {"job_description": "x" * 4001}],
)
def test_invalid_requests_are_rejected(tmp_path, change):
    client, _ = make_client(tmp_path)
    assert client.post("/api/runs", json={**GOOD_RUN, **change}).status_code == 422


def test_whitespace_only_company_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/runs", json={**GOOD_RUN, "company": "   "}).status_code == 422


def test_live_run_streams_every_agent_over_sse(tmp_path, fake_search):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/runs", json=GOOD_RUN)
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    events = read_sse(client, run_id)
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-1] == "run_completed"
    for key in ("researcher", "analyst", "questioner", "coach"):
        assert any(e["type"] == "task_completed" and e["agent"] == key for e in events)
    assert sum(t == "tool_finished" for t in types) == 2
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)

    summary = client.get(f"/api/runs/{run_id}").json()
    assert summary["status"] == "completed"
    assert set(summary["report"]) == {"researcher", "analyst", "questioner", "coach"}


def test_sse_resumes_after_last_event_id(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    run_id = client.post("/api/runs", json=GOOD_RUN).json()["id"]
    wait_until_done(manager.get(run_id))
    all_events = read_sse(client, run_id)
    resume_from = all_events[len(all_events) // 2]["seq"]
    with client.stream("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(resume_from)}) as resp:
        later = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    assert later and all(e["seq"] > resume_from for e in later)
    assert later[-1]["type"] == "run_completed"


def test_report_downloads_as_markdown(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    run_id = client.post("/api/runs", json=GOOD_RUN).json()["id"]
    wait_until_done(manager.get(run_id))
    resp = client.get(f"/api/runs/{run_id}/report.md")
    assert resp.status_code == 200
    assert 'filename="interview-prep-data-analyst-at-acme-corp.md"' in resp.headers["content-disposition"]
    assert "# Interview Prep: Data Analyst at Acme Corp" in resp.text
    assert "## Answer Guide" in resp.text


def test_only_one_live_run_at_a_time(tmp_path, fake_search):
    client, manager = make_client(tmp_path, delay=0.3)
    first = client.post("/api/runs", json=GOOD_RUN)
    second = client.post("/api/runs", json=GOOD_RUN)
    assert first.status_code == 201
    assert second.status_code == 409
    wait_until_done(manager.get(first.json()["id"]))
    third = client.post("/api/runs", json=GOOD_RUN)
    assert third.status_code == 201
    wait_until_done(manager.get(third.json()["id"]))


def test_live_run_refused_when_model_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    claude = Settings(model="anthropic/claude-opus-5-5", max_tokens=1000, ollama_host="")
    client, _ = make_client(tmp_path, settings=claude)
    resp = client.post("/api/runs", json=GOOD_RUN)
    assert resp.status_code == 400 and "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_runs_are_listed_newest_first_without_reports(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    assert client.get("/api/runs").json() == []
    first = client.post("/api/runs", json=GOOD_RUN).json()["id"]
    wait_until_done(manager.get(first))
    second = client.post("/api/runs", json={**GOOD_RUN, "company": "Globex"}).json()["id"]
    wait_until_done(manager.get(second))
    runs = client.get("/api/runs").json()
    assert [r["id"] for r in runs] == [second, first]
    assert runs[0]["inputs"]["company"] == "Globex" and runs[0]["status"] == "completed"
    assert "report" not in runs[0]


def test_unknown_run_is_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404
