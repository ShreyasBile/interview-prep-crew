"""Resume personalisation, resume upload, ATS scans, sources, history and stats (through the HTTP API)."""

import json

import pytest

from app.config import Settings
from tests.conftest import wait_until_done
from tests.fake_llm import PROMPTS_SEEN
from tests.samples import GOOD_RESUME, JOB_DESCRIPTION, POOR_RESUME
from tests.test_api import GOOD_RUN, make_client, read_sse

RESUME_TOKEN = "Zephyr-Quokka-7731"
PERSONAL_RESUME = f"Built the {RESUME_TOKEN} pipeline in Python. " + GOOD_RESUME
ATS_BODY = {"resume": GOOD_RESUME, "job_description": JOB_DESCRIPTION, "role": "Backend Engineer", "filename": "aarav.pdf"}


# ---------- resume personalisation ----------


def test_resume_is_given_to_the_agents_but_never_stored(tmp_path, fake_search):
    client, manager = make_client(tmp_path, store=True)
    resp = client.post("/api/runs", json={**GOOD_RUN, "resume": PERSONAL_RESUME})
    assert resp.status_code == 201
    run = wait_until_done(manager.get(resp.json()["id"]))

    sent = {}
    for role, text in PROMPTS_SEEN:
        sent[role] = sent.get(role, "") + text
    for role in ("Role Analyst", "Question Generator", "Answer Coach"):
        assert RESUME_TOKEN in sent[role]  # the model really received the resume
    assert RESUME_TOKEN not in sent["Company Researcher"]  # research needs no personal data

    shown = {e["agent"]: e["task_prompt"] for e in run.events if e["type"] == "agent_started"}
    assert all(RESUME_TOKEN not in prompt for prompt in shown.values())
    assert "[resume hidden:" in shown["analyst"]  # the UI says it was withheld

    assert run.inputs["has_resume"] is True and run.inputs["resume_words"] > 100
    assert "resume" not in run.inputs
    stored = (tmp_path / "runs" / f"{run.id}.json").read_text(encoding="utf-8")
    assert RESUME_TOKEN not in stored and "Aarav" not in stored
    assert RESUME_TOKEN not in json.dumps(run.summary()) + client.get(f"/api/runs/{run.id}/report.md").text


def test_prep_without_a_resume_is_marked_as_such(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    run = wait_until_done(manager.get(client.post("/api/runs", json=GOOD_RUN).json()["id"]))
    assert run.inputs["has_resume"] is False and run.inputs["has_job_description"] is False
    assert "Personalised" not in run.to_markdown()


def test_oversized_resume_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/runs", json={**GOOD_RUN, "resume": "x" * 12001}).status_code == 422


# ---------- resume upload ----------


def test_resume_text_can_be_extracted_from_an_upload(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/resume/parse?filename=cv.txt", content=GOOD_RESUME.encode())
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "cv.txt" and body["words"] > 250 and "Nimbus Labs" in body["text"]


@pytest.mark.parametrize(
    "filename, content, status",
    [
        pytest.param("cv.exe", b"x" * 200, 422, id="unsupported-type"),
        pytest.param("cv.txt", b"", 422, id="empty"),
        pytest.param("cv.txt", b"two words", 422, id="too-little-text"),
        pytest.param("cv.txt", b"a" * (5 * 1024 * 1024 + 6000), 413, id="over-5mb"),
    ],
)
def test_bad_uploads_are_refused(tmp_path, filename, content, status):
    client, _ = make_client(tmp_path)
    assert client.post(f"/api/resume/parse?filename={filename}", content=content).status_code == status


# ---------- ATS scan ----------


def test_ats_scan_without_review_is_instant_and_complete(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/ats", json={**ATS_BODY, "review": False})
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "ats" and body["status"] == "completed"
    assert body["score"]["score"] >= 90 and body["review_skipped"] is None
    assert body["inputs"] == {
        "role": "Backend Engineer",
        "filename": "aarav.pdf",
        "has_job_description": True,
        "resume_words": len(GOOD_RESUME.split()),
    }
    events = read_sse(client, body["id"])
    assert [e["type"] for e in events] == ["run_started", "run_completed"]
    assert events[0]["score"]["score"] == body["score"]["score"] and events[0]["review"] is False


def test_ats_scan_with_review_runs_the_reviewer_agent(tmp_path):
    client, manager = make_client(tmp_path)
    body = client.post("/api/ats", json=ATS_BODY).json()
    assert body["status"] == "running" and body["score"]["score"] >= 90
    run = wait_until_done(manager.get(body["id"]))
    assert run.status == "completed", run.error
    assert set(run.report) == {"ats_reviewer"}
    events = read_sse(client, run.id)
    assert events[0]["agents"][0]["key"] == "ats_reviewer" and events[0]["review"] is True
    assert any(e["type"] == "task_completed" and e["agent"] == "ats_reviewer" for e in events)


def test_ats_review_is_skipped_when_the_model_is_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    groq = Settings(model="groq/openai/gpt-oss-120b", max_tokens=1000, ollama_host="")
    client, _ = make_client(tmp_path, settings=groq)
    body = client.post("/api/ats", json=ATS_BODY).json()
    assert body["status"] == "completed" and body["score"]["score"] >= 90  # the score never needs a model
    assert "GROQ_API_KEY" in body["review_skipped"]


def test_ats_review_is_skipped_while_another_crew_is_running(tmp_path, fake_search):
    client, manager = make_client(tmp_path, delay=0.3)
    prep = client.post("/api/runs", json=GOOD_RUN).json()
    body = client.post("/api/ats", json=ATS_BODY).json()
    assert body["status"] == "completed" and "already in progress" in body["review_skipped"]
    wait_until_done(manager.get(prep["id"]))


def test_ats_scan_rejects_resumes_that_are_too_short(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/api/ats", json={"resume": "Only a few words."})
    assert resp.status_code == 422 and "too short" in resp.json()["detail"]


def test_ats_report_downloads_as_markdown(tmp_path):
    client, manager = make_client(tmp_path)
    run_id = client.post("/api/ats", json=ATS_BODY).json()["id"]
    wait_until_done(manager.get(run_id))
    resp = client.get(f"/api/runs/{run_id}/report.md")
    assert 'filename="resume-report-resume-scan-aarav-pdf.md"' in resp.headers["content-disposition"]
    text = resp.text
    assert text.startswith("# Resume ATS Report") and "| Keyword match |" in text
    assert "Missing: kafka, graphql" in text or "Missing: graphql, kafka" in text
    assert "# AI Review" in text and "Add metrics" in text


# ---------- sources, history, stats ----------


def test_sources_are_collected_and_listed_in_the_report(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    run = wait_until_done(manager.get(client.post("/api/runs", json=GOOD_RUN).json()["id"]))
    urls = [s["url"] for s in run.sources]
    assert urls == ["https://acme.example/careers", "https://acme.example/interview"]  # de-duplicated across agents
    assert run.sources[0]["agent"] == "researcher" and run.sources[0]["tool"] == "web_search"
    assert "# Sources" in run.to_markdown() and "(https://acme.example/careers)" in run.to_markdown()
    assert read_sse(client, run.id)[-1]["sources"] == run.sources


def test_finished_runs_survive_a_restart(tmp_path, fake_search):
    client, manager = make_client(tmp_path, store=True)
    prep = wait_until_done(manager.get(client.post("/api/runs", json=GOOD_RUN).json()["id"]))
    scan = client.post("/api/ats", json={**ATS_BODY, "review": False}).json()
    assert len(list((tmp_path / "runs").glob("*.json"))) == 2

    reborn_client, reborn = make_client(tmp_path, store=True)  # a fresh process reading the same folder
    assert {r["id"] for r in reborn_client.get("/api/runs").json()} == {prep.id, scan["id"]}
    restored = reborn.get(prep.id)
    assert restored.report == prep.report and restored.sources == prep.sources
    # the activity log replays, and its sequence numbers match list positions again
    events = read_sse(reborn_client, prep.id)
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_completed"
    assert [e["seq"] for e in restored.events] == list(range(1, len(restored.events) + 1))
    assert reborn_client.get(f"/api/runs/{scan['id']}").json()["score"]["score"] == scan["score"]["score"]


def test_runs_can_be_deleted_from_history(tmp_path, fake_search):
    client, manager = make_client(tmp_path, store=True)
    run_id = client.post("/api/runs", json=GOOD_RUN).json()["id"]
    wait_until_done(manager.get(run_id))
    assert (tmp_path / "runs" / f"{run_id}.json").exists()
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert not (tmp_path / "runs" / f"{run_id}.json").exists()
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.delete(f"/api/runs/{run_id}").status_code == 404


def test_a_running_run_cannot_be_deleted(tmp_path, fake_search):
    client, manager = make_client(tmp_path, delay=0.3)
    run_id = client.post("/api/runs", json=GOOD_RUN).json()["id"]
    assert client.delete(f"/api/runs/{run_id}").status_code == 409
    wait_until_done(manager.get(run_id))


def test_history_can_be_filtered_by_kind(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    wait_until_done(manager.get(client.post("/api/runs", json=GOOD_RUN).json()["id"]))
    client.post("/api/ats", json={**ATS_BODY, "review": False})
    assert [r["kind"] for r in client.get("/api/runs?kind=ats").json()] == ["ats"]
    assert [r["kind"] for r in client.get("/api/runs?kind=prep").json()] == ["prep"]
    assert len(client.get("/api/runs?limit=1").json()) == 1
    assert client.get("/api/runs?kind=other").status_code == 422
    brief = client.get("/api/runs?kind=ats").json()[0]
    assert "report" not in brief and brief["score"].keys() == {"score", "grade"}


def test_stats_summarise_all_runs(tmp_path, fake_search):
    client, manager = make_client(tmp_path)
    empty = client.get("/api/stats").json()
    assert empty["preps"] == 0 and empty["scans"] == 0 and empty["avg_score"] is None and empty["score_trend"] == []

    wait_until_done(manager.get(client.post("/api/runs", json=GOOD_RUN).json()["id"]))
    good = client.post("/api/ats", json={**ATS_BODY, "review": False}).json()["score"]["score"]
    poor = client.post("/api/ats", json={"resume": POOR_RESUME, "review": False}).json()["score"]["score"]
    stats = client.get("/api/stats").json()
    assert stats["preps"] == 1 and stats["scans"] == 2
    assert stats["best_score"] == good and stats["avg_score"] == round((good + poor) / 2)
    assert [t["score"] for t in stats["score_trend"]] == [good, poor]  # oldest first
    assert stats["tool_calls"] == 2 and stats["agent_steps"] >= 8 and stats["sources"] == 2
    assert stats["avg_prep_seconds"] is not None
