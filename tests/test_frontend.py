"""Frontend checks run with Node (skipped when Node is not installed)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
STATIC = Path(__file__).resolve().parent.parent / "static"
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def render(md: str) -> str:
    script = (
        "global.window = {}; require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(window.MD.render(require('fs').readFileSync(0, 'utf8'))));"
    )
    out = subprocess.run(
        [NODE, "-e", script, str(STATIC / "markdown.js")], input=md, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(out.stdout)


@pytest.mark.parametrize("name", ["app.js", "markdown.js"])
def test_scripts_have_valid_syntax(name):
    subprocess.run([NODE, "--check", str(STATIC / name)], check=True)


def test_model_html_is_escaped():
    html = render('<script>alert(1)</script><img src=x onerror="hack()">')
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_only_http_links_become_anchors():
    html = render("[ok](https://a.example) [bad](javascript:alert(1))")
    assert '<a href="https://a.example"' in html
    assert "javascript:" not in html.split("<a")[1].split(">")[0]  # first anchor is the safe one
    assert html.count("<a ") == 1


def test_headings_lists_and_emphasis():
    html = render("## Snapshot\n- **Bold** item\n- *soft* item\n\n1. first\n2. second")
    assert "<h3>Snapshot</h3>" in html
    assert "<ul><li><strong>Bold</strong> item</li><li><em>soft</em> item</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html


def test_tables_render():
    html = render("| Round | Focus |\n|---|---|\n| 1 | Aptitude |")
    assert "<th>Round</th>" in html and "<td>Aptitude</td>" in html


def test_model_wrappers_are_removed():
    assert render("```markdown\n## Title\n```") == "<h3>Title</h3>"
    assert render("<think>private reasoning</think>Answer") == "<p>Answer</p>"
