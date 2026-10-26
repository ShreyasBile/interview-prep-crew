import httpx
import pytest

from app import config
from app.config import Settings, make_llm


def settings(model, host="http://localhost:11434"):
    return Settings(model=model, max_tokens=16000, ollama_host=host)


def test_provider_and_model_name_are_split():
    s = settings("anthropic/claude-opus-5-5")
    assert (s.provider, s.model_name) == ("anthropic", "claude-opus-5-5")


def test_missing_api_key_blocks_live_runs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ready, reason = settings("anthropic/claude-opus-5-5").live_status()
    assert not ready and "ANTHROPIC_API_KEY" in reason


def test_api_key_present_allows_live_runs(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert settings("anthropic/claude-opus-5-5").live_status()[0]


def test_ollama_not_running(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(config.httpx, "get", down)
    ready, reason = settings("ollama/interview-prep-qwen3").live_status()
    assert not ready and "not running" in reason


@pytest.mark.parametrize(
    "installed, ready",
    [(["interview-prep-qwen3:latest"], True), (["qwen3-vl:4b"], False)],
)
def test_ollama_model_must_be_pulled(monkeypatch, installed, ready):
    body = {"models": [{"name": n} for n in installed]}
    monkeypatch.setattr(
        config.httpx, "get", lambda url, **k: httpx.Response(200, json=body, request=httpx.Request("GET", url))
    )
    assert settings("ollama/interview-prep-qwen3").live_status()[0] is ready


def test_claude_requests_never_send_temperature_or_forced_tool_choice(monkeypatch):
    # Claude rejects temperature/top_p (since 2026-10-21) and forced tool_choice on current models.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    llm = make_llm(settings("anthropic/claude-opus-5-5"))
    tool = lambda name: {"type": "function", "function": {"name": name, "description": "d", "parameters": {"type": "object", "properties": {}}}}
    params = llm._prepare_completion_params(
        messages=[{"role": "user", "content": "hi"}], tools=[tool("web_search"), tool("news_search")], available_functions=None
    )
    assert params["model"] == "claude-opus-5-5"
    assert params["max_tokens"] == 16000
    assert params["stream"] is True
    for forbidden in ("temperature", "top_p", "tool_choice"):
        assert forbidden not in params


def test_groq_needs_its_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ready, reason = settings("groq/llama-3.3-70b-versatile").live_status()
    assert not ready and "GROQ_API_KEY" in reason


@pytest.mark.parametrize("model_name", ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"])
def test_groq_uses_its_openai_compatible_endpoint(monkeypatch, model_name):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    llm = make_llm(settings(f"groq/{model_name}"))
    assert llm.model == model_name  # Groq model ids may contain a slash themselves
    assert llm.base_url == config.GROQ_BASE_URL
    assert llm.api_key == "test-key"
    params = llm._prepare_completion_params(messages=[{"role": "user", "content": "hi"}])
    assert params["model"] == model_name
    assert params["stream"] is True
    assert params["max_tokens"] == config.GROQ_MAX_TOKENS
    assert llm.max_retries == config.GROQ_MAX_RETRIES  # free tier rate-limits a full crew run


@pytest.mark.parametrize("model_name, effort", [("openai/gpt-oss-120b", "low"), ("qwen/qwen3.8-27b", None)])
def test_groq_reasoning_models_think_briefly(monkeypatch, model_name, effort):
    # reasoning tokens count against Groq's per-minute budget
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    params = make_llm(settings(f"groq/{model_name}"))._prepare_completion_params(
        messages=[{"role": "user", "content": "hi"}]
    )
    assert params.get("reasoning_effort") == effort


def test_ollama_llm_points_at_local_server():
    llm = make_llm(settings("ollama/interview-prep-qwen3", host="http://localhost:11434"))
    assert llm.model.endswith("interview-prep-qwen3")
    assert "localhost:11434" in (llm.base_url or "")
