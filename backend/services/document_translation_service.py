import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Tuple

from docx import Document

from backend.services.file_reader_service import read_plain_text, extract_text_from_file, extract_csv_text
from backend.services.language_service import detect_text_language
from backend.services.translation_service import translate_with_views, normalize_lang


SUPPORTED_FORMAT_PRESERVE_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}




def _font_candidates() -> list[Path]:
    candidates = [
        Path(r"C:\Windows\Fonts\Nirmala.ttf"),
        Path(r"C:\Windows\Fonts\NirmalaB.ttf"),
        Path(r"C:\Windows\Fonts\NirmalaS.ttf"),
        Path(r"C:\Windows\Fonts\Mangal.ttf"),
        Path(r"C:\Windows\Fonts\Kokila.ttf"),
        Path(r"C:\Windows\Fonts\Aparajita.ttf"),
        Path(r"C:\Windows\Fonts\Utsaah.ttf"),
        Path(r"C:\Windows\Fonts\arialuni.ttf"),
        Path(r"C:\Windows\Fonts\NirmalaUI.ttf"),
        Path(r"C:\Windows\Fonts\Nirmala.ttc"),
        Path(r"C:\Windows\Fonts\mangal.ttf"),
        Path(r"C:\Windows\Fonts\kokila.ttf"),
        Path(r"C:\Windows\Fonts\utsaah.ttf"),
        Path(r"C:\Windows\Fonts\aparaj.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagariUI.ttf"),
        Path("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for font_dir in [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]:
        if font_dir.exists():
            patterns = [
                "*Nirmala*.ttf", "*Nirmala*.ttc", "*Nirmala*.otf", "*Mangal*.ttf", "*Mangal*.ttc", "*NotoSansDevanagari*.ttf", "*NotoSansDevanagari*.otf",
                "*Lohit*Devanagari*.ttf", "*Kokila*.ttf", "*Kokila*.ttc", "*Aparajita*.ttf", "*Aparaj*.ttf",
                "*Utsaah*.ttf", "*FreeSerif*.ttf", "*DejaVuSans.ttf",
            ]
            for pattern in patterns:
                candidates.extend(font_dir.rglob(pattern))
    seen = set()
    unique = []
    for item in candidates:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _pdf_font_path() -> Path | None:
    for font_path in _font_candidates():
        if font_path.exists():
            return font_path
    return None

def _pdf_unicode_font_name() -> str:
    """Register a system font for Latin/Devanagari PDF output."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        font_path = _pdf_font_path()
        if font_path is not None:
            name = "LinguaFusionUnicode"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(font_path)))
            return name
    except Exception:
        pass
    return "Helvetica"


def _contains_devanagari(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text or ""))


def _wrap_for_image(draw, text: str, font, max_px: int) -> list[str]:
    words = re.split(r"(\s+)", text.strip())
    lines: list[str] = []
    current = ""
    for token in words:
        candidate = current + token
        try:
            width = draw.textbbox((0, 0), candidate, font=font)[2]
        except Exception:
            width = len(candidate) * 12
        if current and width > max_px:
            lines.append(current.strip())
            current = token.strip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    out: list[str] = []
    for line in lines:
        try:
            width = draw.textbbox((0, 0), line, font=font)[2]
        except Exception:
            width = len(line) * 12
        if width <= max_px:
            out.append(line)
            continue
        chunk = ""
        for ch in line:
            candidate = chunk + ch
            try:
                cwidth = draw.textbbox((0, 0), candidate, font=font)[2]
            except Exception:
                cwidth = len(candidate) * 12
            if chunk and cwidth > max_px:
                out.append(chunk)
                chunk = ch
            else:
                chunk = candidate
        if chunk:
            out.append(chunk)
    return out or [text]


def _append_pdf_text(story, text: str, style, available_width_pt: float = 470):
    """Append text to a ReportLab story, rendering Devanagari lines as images.

    ReportLab Paragraph can produce black boxes for Devanagari on some Windows
    setups even when a Unicode font is available. Rendering only Devanagari
    lines through Pillow avoids those black boxes while keeping normal text and
    tables as selectable ReportLab text.
    """
    clean = (text or "").strip()
    if not clean:
        return
    if not _contains_devanagari(clean):
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape
        story.append(Paragraph(escape(clean), style))
        return

    font_path = _pdf_font_path()
    if font_path is None:
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape
        story.append(Paragraph(escape(clean), style))
        return

    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        from reportlab.platypus import Image as RLImage
        from tempfile import NamedTemporaryFile
        scale = 2
        max_px = int(available_width_pt * scale)
        font_size = max(20, int(float(getattr(style, "fontSize", 10) or 10) * scale * 1.35))
        font = ImageFont.truetype(str(font_path), font_size)
        dummy = PILImage.new("RGB", (max_px, 10), "white")
        draw = ImageDraw.Draw(dummy)
        lines = _wrap_for_image(draw, clean, font, max_px - 20)
        line_h = int(font_size * 1.45)
        img_h = max(line_h + 16, line_h * len(lines) + 16)
        img = PILImage.new("RGB", (max_px, img_h), "white")
        draw = ImageDraw.Draw(img)
        y = 6
        for line in lines:
            draw.text((4, y), line, fill="black", font=font)
            y += line_h
        tmp = NamedTemporaryFile(delete=False, suffix=".png")
        tmp.close()
        img.save(tmp.name)
        story.append(RLImage(tmp.name, width=available_width_pt, height=img_h / scale))
    except Exception:
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape
        story.append(Paragraph(escape(clean), style))



def _devanagari_pdf_font_path() -> Path | None:
    """Return a font that is known to contain real Devanagari glyphs.

    Do not fall back to generic Latin fonts such as DejaVuSans here: those can
    render Hindi as black boxes, which is worse than a controlled export error.
    """
    preferred_patterns = (
        "nirmala", "mangal", "notosansdevanagari", "lohit-devanagari",
        "kokila", "aparajita", "utsaah"
    )
    candidates = [p for p in _font_candidates() if any(pattern in p.name.lower() for pattern in preferred_patterns)]
    for font_path in candidates:
        if not font_path.exists():
            continue
        try:
            from PIL import Image, ImageDraw, ImageFont
            sample = "कृपया हिंदी परीक्षण"
            font = ImageFont.truetype(str(font_path), 34)
            img = Image.new("RGB", (520, 110), "white")
            draw = ImageDraw.Draw(img)
            draw.text((12, 20), sample, fill="black", font=font)
            # A valid Devanagari font creates many ink pixels. A tofu/box-only
            # rendering creates only a few repeated rectangular outlines. This
            # threshold is intentionally conservative.
            gray = img.convert("L")
            pixels = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
            ink = sum(1 for px in pixels if px < 245)
            if ink > 1200:
                return font_path
        except Exception:
            continue
    return None


def _latin_pdf_image_font_path() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\SegoeUI.ttf"),
        Path(r"C:\Windows\Fonts\Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _script_runs(text: str):
    for match in re.finditer(r"[\u0900-\u097F\u200c\u200d]+|[^\u0900-\u097F\u200c\u200d]+", text or ""):
        run = match.group(0)
        if run:
            yield run, bool(re.search(r"[\u0900-\u097F]", run))


def _measure_mixed_text(draw, text: str, font_latin, font_deva) -> int:
    width = 0
    for run, is_deva in _script_runs(text):
        font = font_deva if is_deva else font_latin
        try:
            bbox = draw.textbbox((0, 0), run, font=font)
            width += max(0, bbox[2] - bbox[0])
        except Exception:
            width += len(run) * 12
    return width


def _draw_mixed_text(draw, xy, text: str, font_latin, font_deva, fill="black"):
    x, y = xy
    for run, is_deva in _script_runs(text):
        font = font_deva if is_deva else font_latin
        draw.text((x, y), run, fill=fill, font=font)
        try:
            bbox = draw.textbbox((0, 0), run, font=font)
            x += max(0, bbox[2] - bbox[0])
        except Exception:
            x += len(run) * 12

def _wrap_text_pixels(draw, text: str, font_latin, font_deva, max_px: int) -> list[str]:
    words = re.split(r"(\s+)", (text or "").strip())
    lines: list[str] = []
    current = ""
    for token in words:
        candidate = current + token
        if current and _measure_mixed_text(draw, candidate, font_latin, font_deva) > max_px:
            lines.append(current.strip())
            current = token.strip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    out: list[str] = []
    for line in lines or [""]:
        if _measure_mixed_text(draw, line, font_latin, font_deva) <= max_px:
            out.append(line)
            continue
        chunk = ""
        for ch in line:
            candidate = chunk + ch
            if chunk and _measure_mixed_text(draw, candidate, font_latin, font_deva) > max_px:
                out.append(chunk)
                chunk = ch
            else:
                chunk = candidate
        if chunk:
            out.append(chunk)
    return out or [""]

def _write_devanagari_safe_image_pdf(text: str, output_suffix: str, title: str = "LinguaFusion Translation") -> Path | None:
    """Create an image-based PDF for Devanagari-heavy exports.

    ReportLab/Windows font fallback can show Hindi as black boxes. For Hindi
    PDF exports, an image-based PDF is preferable to an unreadable PDF. This is
    used only when Devanagari is present and the requested output is PDF.
    """
    if output_suffix != ".pdf":
        return None
    from backend.services.complex_script_pdf_service import contains_complex_script, write_unicode_pdf
    if contains_complex_script(text or ""):
        return write_unicode_pdf(text, title)
    if not _contains_devanagari(text or ""):
        return None
    font_deva_path = _devanagari_pdf_font_path()
    font_latin_path = _latin_pdf_image_font_path()
    if font_deva_path is None or font_latin_path is None:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
        out = Path(NamedTemporaryFile(delete=False, suffix=".pdf").name)
        dpi = 150
        page_w, page_h = 1240, 1754
        margin_x, margin_y = 90, 80
        max_w = page_w - 2 * margin_x
        font_body_latin = ImageFont.truetype(str(font_latin_path), 28)
        font_body_deva = ImageFont.truetype(str(font_deva_path), 28, layout_engine=getattr(ImageFont, "Layout", ImageFont).RAQM if hasattr(getattr(ImageFont, "Layout", None), "RAQM") else None)
        font_title_latin = ImageFont.truetype(str(font_latin_path), 42)
        font_title_deva = ImageFont.truetype(str(font_deva_path), 42, layout_engine=getattr(ImageFont, "Layout", ImageFont).RAQM if hasattr(getattr(ImageFont, "Layout", None), "RAQM") else None)
        line_h = 44
        gap = 18
        pages = []

        def new_page():
            img = Image.new("RGB", (page_w, page_h), "white")
            return img, ImageDraw.Draw(img), margin_y

        img, draw, y = new_page()
        _draw_mixed_text(draw, (margin_x, y), title, font_title_latin, font_title_deva)
        y += 72
        for block in (text or "").splitlines():
            if not block.strip():
                y += gap
                continue
            wrapped = _wrap_text_pixels(draw, block.strip(), font_body_latin, font_body_deva, max_w)
            for line in wrapped:
                if y + line_h > page_h - margin_y:
                    pages.append(img)
                    img, draw, y = new_page()
                _draw_mixed_text(draw, (margin_x, y), line, font_body_latin, font_body_deva)
                y += line_h
            y += 8
        pages.append(img)
        pages[0].save(out, "PDF", resolution=dpi, save_all=True, append_images=pages[1:])
        return out
    except Exception:
        return None




def _resolve_source_language(text: str, source_lang: str) -> str:
    """Resolve Auto only once per document/export request."""
    src = normalize_lang(source_lang or "auto")
    if src and src != "auto":
        return src
    detected = detect_text_language(text or "")
    if detected.get("ok") and detected.get("language"):
        return normalize_lang(detected.get("language"))
    return "en"


def _looks_atomic_value(text: str) -> bool:
    """Return True for values that should not be translated inside tables."""
    value = (text or "").strip()
    if not value:
        return True
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?(?:\s*(?:EUR|USD|GBP|%|GHz|MHz|kHz|dBm|ns|min|kg|bar|pcs))?", value, re.I):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|[A-Z]-?\d+[A-Z0-9-]*|N/A", value, re.I):
        return True
    if re.fullmatch(r"[A-Z]{2,}(?:[/-][A-Z0-9]+)*", value):
        return True
    return False


def _translate_piece(text: str, source_lang: str, target_lang: str, cache: Dict[Tuple[str, str, str], str]) -> str:
    """Translate a small text piece with a safe fallback.

    Document export should never fail because one cell/line has a weak route.
    If the local translation route fails, preserve the original text rather than
    breaking the export workflow.
    """
    clean = (text or "").strip()
    if not clean or _looks_atomic_value(clean):
        return clean
    key = (clean, source_lang, target_lang)
    if key in cache:
        return cache[key]
    try:
        result = translate_with_views(clean, source_lang, target_lang)
        translated = (result.get("translated_text") or "").strip() if result.get("ok") else ""
        if not translated:
            translated = clean
    except Exception:
        translated = clean
    cache[key] = translated
    return translated


def _is_pipe_separator(line: str) -> bool:
    cells = [cell.strip() for cell in (line or "").strip().strip("|").split("|")]
    return len(cells) >= 2 and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def _is_pipe_table_line(line: str) -> bool:
    value = (line or "").strip()
    if not value or "|" not in value:
        return False
    if _is_pipe_separator(value):
        return True
    cells = [cell.strip() for cell in value.strip("|").split("|")]
    return len(cells) >= 2 and any(cells)


def _split_pipe_cells(line: str) -> list[str]:
    return [cell.strip() for cell in (line or "").strip().strip("|").split("|")]


def _translate_line_preserving_pipes(line: str, source_lang: str, target_lang: str, cache: Dict[Tuple[str, str, str], str]) -> str:
    if _is_pipe_separator(line):
        return line
    cells = _split_pipe_cells(line)
    translated_cells = [_translate_piece(cell, source_lang, target_lang, cache) for cell in cells]
    return " | ".join(translated_cells)


def translate_text_file_preserving_lines(file_path: Path, source_lang: str, target_lang: str, output_suffix: str) -> Path:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        text = extract_csv_text(file_path)
    else:
        text = read_plain_text(file_path)
    return translate_extracted_text_preserving_blocks(text, source_lang, target_lang, output_suffix, title="LinguaFusion Translation")

def _blocks_with_pipe_tables(text: str):
    """Yield ('paragraph', str) or ('table', rows) while preserving table runs."""
    lines = (text or "").splitlines()
    i = 0
    paragraph_buffer: list[str] = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            payload = "\n".join(paragraph_buffer).strip()
            paragraph_buffer = []
            if payload:
                return ("paragraph", payload)
        return None

    while i < len(lines):
        line = lines[i]
        if _is_pipe_table_line(line):
            flushed = flush_paragraph()
            if flushed:
                yield flushed
            rows = []
            while i < len(lines) and (_is_pipe_table_line(lines[i]) or _is_pipe_separator(lines[i])):
                if not _is_pipe_separator(lines[i]):
                    rows.append(_split_pipe_cells(lines[i]))
                i += 1
            if rows:
                max_cols = max(len(row) for row in rows)
                rows = [row + [""] * (max_cols - len(row)) for row in rows]
                yield ("table", rows)
            continue
        if line.strip():
            paragraph_buffer.append(line)
        else:
            flushed = flush_paragraph()
            if flushed:
                yield flushed
        i += 1
    flushed = flush_paragraph()
    if flushed:
        yield flushed

def _write_translated_text_output(translated_text: str, output_suffix: str, title: str = "LinguaFusion Translation") -> Path:
    if output_suffix == ".docx":
        out = Path(NamedTemporaryFile(delete=False, suffix=".docx").name)
        doc = Document()
        doc.add_heading(title, level=1)
        for block_type, payload in _blocks_with_pipe_tables(translated_text):
            if block_type == "table":
                rows = payload
                if not rows:
                    continue
                table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                table.style = "Table Grid"
                for r_idx, row in enumerate(rows):
                    for c_idx, value in enumerate(row):
                        table.cell(r_idx, c_idx).text = value
                doc.add_paragraph("")
            else:
                for line in str(payload).splitlines():
                    doc.add_paragraph(line)
        doc.save(out)
        return out

    if output_suffix == ".pdf":
        image_pdf = _write_devanagari_safe_image_pdf(translated_text, output_suffix, title=title)
        if image_pdf is not None:
            return image_pdf
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from xml.sax.saxutils import escape

        out = Path(NamedTemporaryFile(delete=False, suffix=".pdf").name)
        pdf = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        unicode_font = _pdf_unicode_font_name()
        for style_name in ["Normal", "BodyText", "Title", "Heading1", "Heading2"]:
            if style_name in styles:
                styles[style_name].fontName = unicode_font
        story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 0.35*cm)]
        for block_type, payload in _blocks_with_pipe_tables(translated_text):
            if block_type == "table":
                rows = payload
                table_data = [[Paragraph(escape(str(cell)), styles["BodyText"]) for cell in row] for row in rows]
                table = Table(table_data, repeatRows=1)
                table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(table)
                story.append(Spacer(1, 0.25*cm))
            else:
                for line in str(payload).splitlines():
                    if line.strip():
                        _append_pdf_text(story, line.strip(), styles["BodyText"])
                        story.append(Spacer(1, 0.12*cm))
                story.append(Spacer(1, 0.12*cm))
        pdf.build(story)
        return out

    out = Path(NamedTemporaryFile(delete=False, suffix=".txt").name)
    out.write_text(translated_text, encoding="utf-8")
    return out

def translate_extracted_text_preserving_blocks(text: str, source_lang: str, target_lang: str, output_suffix: str, title: str = "LinguaFusion Translation") -> Path:
    resolved_source = _resolve_source_language(text, source_lang)
    cache: Dict[Tuple[str, str, str], str] = {}
    translated_blocks = []
    for block in text.split("\n\n"):
        if not block.strip():
            translated_blocks.append("")
            continue
        translated_lines = []
        for line in block.splitlines():
            if not line.strip():
                translated_lines.append("")
            else:
                leading = line[: len(line) - len(line.lstrip())]
                trailing = line[len(line.rstrip()):]
                if "|" in line:
                    translated_lines.append(_translate_line_preserving_pipes(line, resolved_source, target_lang, cache))
                else:
                    translated_lines.append(leading + _translate_piece(line.strip(), resolved_source, target_lang, cache) + trailing)
        translated_blocks.append("\n".join(translated_lines))
    return _write_translated_text_output("\n\n".join(translated_blocks), output_suffix, title=title)


def translate_document_preserving_format(file_path: Path, source_lang: str, target_lang: str, output_format: str) -> Path:
    output_format = output_format.lower().strip().lstrip(".")
    if output_format not in {"txt", "docx", "pdf"}:
        raise ValueError("Format-preserving export currently supports TXT, DOCX and PDF.")

    suffix = file_path.suffix.lower()
    output_suffix = f".{output_format}"

    if suffix == ".docx":
        return translate_docx_preserving_layout(file_path, source_lang, target_lang, output_suffix)

    if suffix in {".txt", ".md", ".csv"}:
        return translate_text_file_preserving_lines(file_path, source_lang, target_lang, output_suffix)

    if suffix == ".pdf":
        extracted = extract_text_from_file(file_path, source_lang)
        if not extracted.get("ok"):
            raise ValueError(extracted.get("error") or "PDF text extraction failed.")
        return translate_extracted_text_preserving_blocks(extracted.get("text", ""), source_lang, target_lang, output_suffix, title="LinguaFusion PDF Translation")

    raise ValueError(f"Format-preserving export is not available for {suffix} yet. Use normal export for this file type.")
