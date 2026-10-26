import httpx

from app import tools
from app.tools import NewsSearchTool, ReadWebpageTool, WebSearchTool, format_results, html_to_text
from tests.conftest import FAKE_NEWS, FAKE_WEB


def test_format_web_results_lists_title_link_and_snippet():
    text = format_results(FAKE_WEB, "web")
    assert text.splitlines()[0] == "1. Life at Acme"
    assert "https://acme.example/careers" in text
    assert "Acme values curiosity." in text


def test_format_news_results_shows_source_and_date():
    text = format_results(FAKE_NEWS, "news")
    assert "1. Acme launches Acme Cloud (News Example | 2026-09-30)" in text
    assert "https://news.example/acme" in text


def test_format_empty_results_suggests_retry():
    assert "No web results" in format_results([], "web")


def test_search_tools_use_duckduckgo(fake_search):
    assert "Life at Acme" in WebSearchTool()._run("Acme culture")
    assert "Acme launches Acme Cloud" in NewsSearchTool()._run("Acme")


def test_search_failure_returns_message_instead_of_crashing(monkeypatch):
    class Down:
        def text(self, *a, **k):
            raise ConnectionError("offline")

    monkeypatch.setattr(tools, "DDGS", Down)
    result = WebSearchTool()._run("anything")
    assert result.startswith("Web search failed (ConnectionError)")


def test_shorter_queries_keep_the_leading_words():
    assert tools.shorter_queries("Infosys recent news 2026 layoffs") == ["Infosys recent news 2026 layoffs", "Infosys recent", "Infosys"]
    assert tools.shorter_queries("Infosys") == ["Infosys"]


def test_news_search_retries_with_a_shorter_query(monkeypatch):
    tried = []

    class PickyNews:
        def news(self, query, max_results=5):
            tried.append(query)
            if len(query.split()) > 2:
                raise RuntimeError("No results found.")  # what ddgs raises for over-long queries
            return FAKE_NEWS

    monkeypatch.setattr(tools, "DDGS", PickyNews)
    result = NewsSearchTool()._run("Acme recent news 2024-2026 leadership changes")
    assert tried == ["Acme recent news 2024-2026 leadership changes", "Acme recent"]
    assert result.startswith('(No results for the full query; showing results for "Acme recent".)')
    assert "Acme launches Acme Cloud" in result


def test_empty_results_also_trigger_the_retry(monkeypatch):
    class Empty:
        def text(self, query, max_results=5):
            return [] if " " in query else FAKE_WEB

    monkeypatch.setattr(tools, "DDGS", Empty)
    assert "Life at Acme" in WebSearchTool()._run("Acme careers culture")


def test_html_to_text_skips_scripts_and_navigation():
    html = "<html><nav>Menu</nav><script>var x=1</script><h1>Careers</h1><p>Join  us\n today</p><footer>(c)</footer></html>"
    assert html_to_text(html) == "Careers Join us today"


def test_read_webpage_rejects_non_http_urls():
    assert "full URL" in ReadWebpageTool()._run("file:///etc/passwd")


def test_read_webpage_retries_with_second_user_agent(monkeypatch):
    seen = []

    def fake_get(url, headers, **kwargs):
        seen.append(headers["User-Agent"])
        status = 403 if len(seen) == 1 else 200
        return httpx.Response(status, text="<p>Interview has three rounds</p>", request=httpx.Request("GET", url))

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    assert ReadWebpageTool()._run("https://acme.example/jobs") == "Interview has three rounds"
    assert seen == list(tools.USER_AGENTS)


def test_read_webpage_reports_http_errors(monkeypatch):
    monkeypatch.setattr(
        tools.httpx, "get", lambda url, **kw: httpx.Response(404, text="", request=httpx.Request("GET", url))
    )
    assert "HTTP 404" in ReadWebpageTool()._run("https://acme.example/missing")


def test_read_webpage_truncates_long_pages(monkeypatch):
    long_html = "<p>" + "word " * 5000 + "</p>"
    monkeypatch.setattr(
        tools.httpx, "get", lambda url, **kw: httpx.Response(200, text=long_html, request=httpx.Request("GET", url))
    )
    text = ReadWebpageTool()._run("https://acme.example/long")
    assert len(text) == tools.MAX_PAGE_CHARS + 1 and text.endswith("…")
