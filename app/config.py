"""Settings read from the environment / .env file.

Import this module before anything from crewai so the telemetry switches below
take effect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

load_dotenv(ROOT / ".env")

# Finished runs are saved here so history survives restarts.
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))

# Keep runs local: no CrewAI telemetry and no trace-upload prompts.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

DEFAULT_MODEL = "anthropic/claude-opus-5-5"

# Which environment variable holds the API key for each provider prefix.
PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}
LOCAL_PROVIDERS = {"ollama", "ollama_chat"}

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Far above any agent's answer (~2K tokens); stops a runaway reply eating the free-tier budget.
GROQ_MAX_TOKENS = 4096
# Groq's free tier allows about 8K tokens per minute and a crew run uses ~30K, so calls hit
# 429 "rate limit" responses. The OpenAI client waits (honouring Retry-After) and retries.
GROQ_MAX_RETRIES = 8


@dataclass(frozen=True)
class Settings:
    model: str
    max_tokens: int
    ollama_host: str

    @property
    def provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else "openai"

    @property
    def model_name(self) -> str:
        return self.model.split("/", 1)[1] if "/" in self.model else self.model

    def live_status(self) -> tuple[bool, str]:
        """Return (ready, human-readable reason) for running the crew for real."""
        if self.provider in LOCAL_PROVIDERS:
            return _ollama_status(self.ollama_host, self.model_name)
        key_env = PROVIDER_KEY_ENV.get(self.provider)
        if key_env and not os.environ.get(key_env):
            return False, f"Set {key_env} in .env to run {self.model} live."
        return True, f"Ready: {self.model}"


def _ollama_status(host: str, model_name: str) -> tuple[bool, str]:
    try:
        resp = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=2.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return False, f"Ollama is not running at {host}. Start it with `ollama serve`."
    names = {m.get("name", "") for m in resp.json().get("models", [])}
    if model_name not in names and f"{model_name}:latest" not in names:
        return False, f"Ollama model '{model_name}' not found. Run `ollama pull {model_name}`."
    return True, f"Ready: local Ollama model {model_name}"


def get_settings() -> Settings:
    return Settings(
        model=os.environ.get("MODEL", DEFAULT_MODEL).strip(),
        max_tokens=int(os.environ.get("MAX_TOKENS", "16000")),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip(),
    )


def make_llm(settings: Settings):
    """Build the CrewAI LLM every agent shares."""
    from crewai import LLM

    if settings.provider == "groq":
        # CrewAI has no native Groq provider, but Groq serves an OpenAI-compatible API,
        # so CrewAI's built-in OpenAI client can talk to it directly.
        groq: dict = {}
        if "gpt-oss" in settings.model_name:
            # gpt-oss reasons before answering and those tokens count against the per-minute
            # budget; "low" is plenty for these writing tasks and works with tool calls.
            groq["reasoning_effort"] = "low"
        return LLM(
            model=f"openai/{settings.model_name}",
            base_url=GROQ_BASE_URL,
            api_key=os.environ.get("GROQ_API_KEY"),
            custom_openai=True,
            stream=True,
            max_tokens=min(settings.max_tokens, GROQ_MAX_TOKENS),
            max_retries=GROQ_MAX_RETRIES,
            **groq,
        )

    kwargs: dict = {"model": settings.model, "stream": True}
    if settings.provider in LOCAL_PROVIDERS:
        kwargs["base_url"] = settings.ollama_host
    else:
        kwargs["max_tokens"] = settings.max_tokens
    return LLM(**kwargs)
