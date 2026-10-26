"""Runs the real crew against the model in .env. Slow and uses the network/model.

    .venv\\Scripts\\python.exe -m pytest -m live -s
"""

import pytest

from app.config import get_settings, make_llm
from app.crew import AGENT_SPECS, build_inputs
from app.events import EventBridge
from app.runs import RunManager
from tests.conftest import wait_until_done

pytestmark = pytest.mark.live


def test_real_model_completes_the_whole_crew(tmp_path):
    settings = get_settings()
    ready, reason = settings.live_status()
    if not ready:
        pytest.skip(reason)
    bridge = EventBridge()
    bridge.install()
    manager = RunManager(bridge, lambda: make_llm(settings), settings.model)
    run = wait_until_done(manager.start_prep(build_inputs("Infosys", "Software Engineer", "Fresher / intern")), timeout=3600)

    assert run.status == "completed", run.error
    assert set(run.report) == {s.key for s in AGENT_SPECS}
    assert any(e["type"] == "tool_finished" and e["agent"] == "researcher" for e in run.events)
    assert all(len(text.split()) > 30 for text in run.report.values())
