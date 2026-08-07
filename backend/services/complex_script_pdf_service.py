"""Unicode-safe PDF export for Arabic, Devanagari, and Odia text.

PyMuPDF Story uses HarfBuzz shaping, avoiding the disconnected Arabic and
black-box Indic output produced by basic ReportLab/Pillow paths on Windows.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from tempfile import NamedTemporaryFile


COMPLEX_SCRIPT_RE = re.compile(
    r"[\u0900-\u097F\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0B00-\u0B7F]"
)
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
INDIC_RE = re.compile(r"[\u0900-\u097F\u0B00-\u0B7F]")
RUN_RE = re.compile(
    r"([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+|[\u0900-\u097F\u0B00-\u0B7F]+)"
)


def contains_complex_script(text: str) -> bool:
    return bool(COMPLEX_SCRIPT_RE.search(text or ""))


def _font_dir() -> Path | None:
    windows_fonts = Path(r"C:\Windows\Fonts")
    if (windows_fonts / "arial.ttf").is_file() and (windows_fonts / "Nirmala.ttc").is_file():
        return windows_fonts
    return None


def _line_html(line: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in RUN_RE.finditer(line or ""):
        parts.append(html.escape(line[cursor:match.start()]))
        run = match.group(0)
        css_class = "arabic" if ARABIC_RE.search(run) else "indic"
        parts.append(f'<span class="{css_class}">{html.escape(run)}</span>')
        cursor = match.end()
    parts.append(html.escape((line or "")[cursor:]))
    direction = "rtl" if len(ARABIC_RE.findall(line or "")) > max(2, len(INDIC_RE.findall(line or ""))) else "auto"
    content = "".join(parts) or "&nbsp;"
    return f'<p dir="{direction}">{content}</p>'


def write_unicode_pdf(text: str, title: str, output_path: Path | str | None = None) -> Path:
    import fitz

    font_dir = _font_dir()
    if font_dir is None:
        raise RuntimeError("Windows Arial and Nirmala fonts are required for multilingual PDF export.")
    if output_path is None:
        output = Path(NamedTemporaryFile(delete=False, suffix=".pdf").name)
    else:
        output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    body = "".join(_line_html(line) for line in (text or "").splitlines())
    document_html = f"<h1>{html.escape(title)}</h1>{body}"
    css = """
        @font-face { font-family: LFArial; src: url(arial.ttf); }
        @font-face { font-family: LFNirmala; src: url(Nirmala.ttc); }
        body { font-family: LFArial; font-size: 11pt; color: #16191d; line-height: 1.45; }
        h1 { font-family: LFArial; font-size: 20pt; color: #1769d2; margin: 0 0 18pt 0; }
        p { margin: 0 0 7pt 0; white-space: pre-wrap; unicode-bidi: plaintext; }
        .arabic { font-family: LFArial; }
        .indic { font-family: LFNirmala; }
    """
    archive = fitz.Archive(str(font_dir))
    story = fitz.Story(html=document_html, user_css=css, archive=archive)
    page_rect = fitz.paper_rect("a4")
    content_rect = page_rect + (54, 54, -54, -54)
    writer = fitz.DocumentWriter(str(output))
    more = True
    try:
        while more:
            device = writer.begin_page(page_rect)
            more, _filled = story.place(content_rect)
            story.draw(device)
            writer.end_page()
    finally:
        writer.close()
    if not output.is_file() or output.stat().st_size < 500:
        raise RuntimeError("Multilingual PDF export did not create a valid file.")
    return output
