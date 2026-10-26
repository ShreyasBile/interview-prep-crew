import pytest

from app import resume
from app.resume import ResumeError, extract_text
from tests.samples import GOOD_RESUME, make_docx, make_pdf

PARAGRAPH = "Built and shipped several backend services in Python with a focus on reliability and speed. " * 2


def test_plain_text_is_cleaned():
    raw = "Name\r\n\r\n\r\n\r\n● Built things fast\r\n" + PARAGRAPH
    text = extract_text("cv.txt", raw.encode("utf-8"))
    assert "\r" not in text and " " not in text
    assert "\n\n\n" not in text
    assert "• Built things fast" in text  # bullet glyph normalised


def test_markdown_files_are_read_like_text():
    assert extract_text("cv.md", ("# Name\n" + PARAGRAPH).encode()).startswith("# Name")


def test_pdf_text_is_extracted():
    lines = ["Aarav Sharma", "Python developer with FastAPI experience"] + [PARAGRAPH.strip()] * 2
    text = extract_text("Resume.PDF", make_pdf(lines))
    assert "Aarav Sharma" in text and "FastAPI experience" in text


def test_docx_text_and_list_bullets_are_extracted():
    data = make_docx([("Aarav Sharma", False), ("Built a REST API with FastAPI", True), (PARAGRAPH.strip(), False)])
    text = extract_text("cv.docx", data)
    assert "Aarav Sharma" in text
    assert "• Built a REST API with FastAPI" in text  # list paragraphs keep their bullet


def test_real_sample_resume_survives_a_pdf_round_trip():
    text = extract_text("cv.pdf", make_pdf(GOOD_RESUME.replace("•", "-").split("\n")))
    assert "Nimbus Labs" in text and "FastAPI" in text


@pytest.mark.parametrize(
    "filename, data, message",
    [
        ("cv.txt", b"", "empty"),
        ("cv.exe", b"x" * 100, "Unsupported"),
        ("cv.png", b"x" * 100, "Unsupported"),
        ("cv.txt", b"too few words", "No readable text"),
        ("cv.pdf", b"this is not a pdf at all", "Could not read this PDF"),
        ("cv.docx", b"this is not a zip", "Could not read this Word file"),
    ],
)
def test_bad_files_give_a_clear_error(filename, data, message):
    with pytest.raises(ResumeError, match=message):
        extract_text(filename, data)


def test_oversized_files_are_refused():
    with pytest.raises(ResumeError, match="5 MB"):
        extract_text("cv.txt", b"a" * (resume.MAX_BYTES + 1))


def test_very_long_text_is_trimmed():
    text = extract_text("cv.txt", (PARAGRAPH * 400).encode())
    assert len(text) == resume.MAX_CHARS
