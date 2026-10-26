"""Tools the research agents can call. DuckDuckGo needs no API key."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx
from crewai.tools import BaseTool
from ddgs import DDGS
from pydantic import BaseModel, Field

MAX_PAGE_CHARS = 3500
# Some sites only accept browser-like agents, others (e.g. Wikipedia) only descriptive ones.
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InterviewPrepCrew/1.0",
    "InterviewPrepCrew/1.0 (student interview-prep project) httpx",
)


class SearchInput(BaseModel):
    query: str = Field(..., description="What to search for, e.g. 'Infosys work culture'")


class PageInput(BaseModel):
    url: str = Field(..., description="Full http(s) URL of the page to read")


def format_results(results: list[dict], kind: str) -> str:
    if not results:
        return f"No {kind} results found. Try a broader query."
    lines = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "").strip()
        link = item.get("href") or item.get("url") or ""
        body = (item.get("body") or item.get("excerpt") or "").strip()
        date = item.get("date", "")
        source = item.get("source", "")
        meta = " | ".join(part for part in (source, date[:10]) if part)
        lines.append(f"{i}. {title}" + (f" ({meta})" if meta else ""))
        lines.append(f"   {link}")
        if body:
            lines.append(f"   {body[:300]}")
    return "\n".join(lines)


RESULT_RE = re.compile(r"^\d+\. (?P<title>.+)\n\s+(?P<url>https?://\S+)", re.M)


def parse_results(text: str) -> list[dict[str, str]]:
    """The (title, url) pairs in text produced by format_results, for the Sources list."""
    return [{"title": m["title"].strip(), "url": m["url"]} for m in RESULT_RE.finditer(text)]


def shorter_queries(query: str) -> list[str]:
    """The query as written, then its first two words, then its first word.

    Models often write long keyword-stuffed queries that match nothing; the company
    name at the front of the query usually still finds good results on its own.
    """
    words = query.split()
    candidates = [query.strip(), " ".join(words[:2]), " ".join(words[:1])]
    return [q for i, q in enumerate(candidates) if q and q not in candidates[:i]]


def search(kind: str, query: str, max_results: int) -> str:
    error = None
    for attempt in shorter_queries(query):
        try:
            method = DDGS().news if kind == "news" else DDGS().text
            results = method(attempt, max_results=max_results)
        except Exception as exc:  # network errors, rate limits, "No results found"
            error = exc
            continue
        if results:
            note = "" if attempt == query.strip() else f'(No results for the full query; showing results for "{attempt}".)\n'
            return note + format_results(results, kind)
    reason = type(error).__name__ if error else "no results"
    return f"{kind.capitalize()} search failed ({reason}). Try another query or continue with what you have."


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web. Returns the top results with title, link and a snippet. "
        "Use it for facts about a company, its products, culture and hiring process."
    )
    args_schema: type[BaseModel] = SearchInput
    max_results: int = 5

    def _run(self, query: str) -> str:
        return search("web", query, self.max_results)


class NewsSearchTool(BaseTool):
    name: str = "news_search"
    description: str = (
        "Search recent news articles. Returns headline, source, date, link and a snippet. "
        "Use short queries such as the company name. Good for launches, results, acquisitions "
        "or leadership changes."
    )
    args_schema: type[BaseModel] = SearchInput
    max_results: int = 5

    def _run(self, query: str) -> str:
        return search("news", query, self.max_results)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "header", "footer", "nav", "form"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


class ReadWebpageTool(BaseTool):
    name: str = "read_webpage"
    description: str = (
        "Read the main text of a web page (first few thousand characters). "
        "Use it on a promising link from web_search, e.g. a careers page or interview guide."
    )
    args_schema: type[BaseModel] = PageInput

    def _run(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "Please pass a full URL starting with http:// or https://"
        error = ""
        for agent in USER_AGENTS:
            try:
                resp = httpx.get(url, timeout=12, follow_redirects=True, headers={"User-Agent": agent})
            except httpx.HTTPError as exc:
                return f"Could not read {url} ({type(exc).__name__}). Try a different link."
            if resp.is_success:
                break
            error = f"HTTP {resp.status_code}"
        else:
            return f"Could not read {url} ({error}). Try a different link."
        text = html_to_text(resp.text)
        if not text:
            return f"{url} had no readable text."
        return text[:MAX_PAGE_CHARS] + ("…" if len(text) > MAX_PAGE_CHARS else "")
