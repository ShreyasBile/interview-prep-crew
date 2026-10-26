"""Turn an uploaded resume (PDF, DOCX, TXT, MD) into plain text."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 5 * 1024 * 1024
MAX_CHARS = 12000
MIN_WORDS = 20
SUPPORTED = (".pdf", ".docx", ".txt", ".md")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BULLET_VARIANTS = re.compile("[•●◦▪■‣⁃·]")


class ResumeError(ValueError):
    """The file could not be turned into usable text; the message is safe to show."""


def extract_text(filename: str, data: bytes) -> str:
    if not data:
        raise ResumeError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ResumeError("The file is larger than 5 MB.")
    name = filename.lower().strip()
    if name.endswith(".pdf"):
        text = _pdf(data)
    elif name.endswith(".docx"):
        text = _docx(data)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8-sig", errors="replace")
    else:
        raise ResumeError("Unsupported file type. Use PDF, DOCX or TXT.")
    text = clean(text)
    if len(text.split()) < MIN_WORDS:
        raise ResumeError(
            "No readable text found. Scanned or image-only files can't be read; paste the text instead."
        )
    return text[:MAX_CHARS]


def clean(text: str) -> str:
    """Normalise line endings, spaces and bullet glyphs so scoring sees consistent text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace("\t", " ")
    text = BULLET_VARIANTS.sub("•", text)
    lines = [re.sub(r"[ ]{2,}", " ", line).rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _pdf(data: bytes) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages[:10]]
    except Exception as exc:  # corrupt, encrypted, not actually a PDF
        raise ResumeError("Could not read this PDF. Try exporting it again or paste the text.") from exc
    return "\n".join(pages)


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ResumeError("Could not read this Word file. Save it as .docx again or paste the text.") from exc
    paragraphs = []
    for para in root.iter(f"{W}p"):
        parts = []
        for node in para.iter():
            if node.tag == f"{W}t" and node.text:
                parts.append(node.text)
            elif node.tag in (f"{W}tab", f"{W}br"):
                parts.append(" ")
        text = "".join(parts).strip()
        if text and para.find(f"{W}pPr/{W}numPr") is not None:  # list item: keep the bullet
            text = "• " + text
        paragraphs.append(text)
    return "\n".join(paragraphs)
