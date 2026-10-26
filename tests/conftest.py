import time

import pytest

import app.config  # noqa: F401  (sets CrewAI telemetry flags before crewai is imported)
from app import tools

FAKE_WEB = [
    {"title": "Life at Acme", "href": "https://acme.example/careers", "body": "Acme values curiosity."},
    {"title": "Acme interview process", "href": "https://acme.example/interview", "body": "Three rounds."},
]
FAKE_NEWS = [
    {"title": "Acme launches Acme Cloud", "url": "https://news.example/acme", "body": "New product.", "date": "2026-09-30T10:00:00", "source": "News Example"},
]


class FakeDDGS:
    def text(self, query, max_results=5):
        return FAKE_WEB[:max_results]

    def news(self, query, max_results=5):
        return FAKE_NEWS[:max_results]


@pytest.fixture(autouse=True)
def clear_prompts_seen():
    from tests.fake_llm import PROMPTS_SEEN

    PROMPTS_SEEN.clear()


@pytest.fixture
def fake_search(monkeypatch):
    """Replace DuckDuckGo so tests never touch the network."""
    monkeypatch.setattr(tools, "DDGS", FakeDDGS)


def wait_until_done(run, timeout=60.0):
    deadline = time.time() + timeout
    while not run.done and time.time() < deadline:
        time.sleep(0.05)
    assert run.done, f"run did not finish within {timeout}s (status={run.status})"
    return run
