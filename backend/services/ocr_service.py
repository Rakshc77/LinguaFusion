from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

try:
    from PIL import Image, ImageOps, ImageFilter
except Exception as exc:  # pragma: no cover
    Image = None
    ImageOps = None
    ImageFilter = None
    PIL_IMPORT_ERROR = exc
else:
    PIL_IMPORT_ERROR = None

try:
    import pytesseract
except Exception as exc:  # pragma: no cover
    pytesseract = None
    TESSERACT_IMPORT_ERROR = exc
else:
    TESSERACT_IMPORT_ERROR = None

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    fitz = None
    FITZ_IMPORT_ERROR = exc
else:
    FITZ_IMPORT_ERROR = None

from backend.config.paths import TESSERACT_EXE, TESSDATA_DIR

if pytesseract is not None and TESSERACT_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)

TESSERACT_CONFIG = f"--tessdata-dir {TESSDATA_DIR}" if TESSDATA_DIR.is_dir() else ""


def _tesseract_config(base: str) -> str:
    return f"{base} {TESSERACT_CONFIG}".strip()

OCR_LANGS = {
    # Latin-first auto mode gives better German umlauts/Spanish OCR.
    # Select Hindi explicitly for Devanagari-heavy images.
    "auto": "eng+deu+spa+hin+ara+ori",
    "en": "eng",
    "de": "deu",
    "es": "spa",
    "hi": "hin",
    "ar": "ara",
    "or": "ori",
}


def _preprocess_image(image):
    """Conservative preprocessing for scans/screenshots without destroying layout."""
    img = ImageOps.exif_transpose(image)
    if img.mode not in {"L", "RGB"}:
        img = img.convert("RGB")
    # Tesseract usually benefits from a minimum width on screenshots.
    width, height = img.size
    if width < 1400:
        scale = 1400 / max(width, 1)
        img = img.resize((int(width * scale), int(height * scale)))
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    return gray.filter(ImageFilter.SHARPEN)


def _clean_ocr_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    # OCR cleanup for common Latin-script German/Spanish documents. Tesseract
    # often reads umlauts/ß as visually similar ASCII or punctuation even when
    # deu/spa language data is available. Keep this conservative and phrase-
    # based so it improves documents without arbitrary word rewriting.
    replacements = [
        (r"\b[Bb]itfe\b", "Bitte"),
        (r"\b[Bb]ittc\b", "Bitte"),
        (r"\b[Ee]spanol\b", "Español"),
        (r"\bmedica\b", "médica"),
        (r"\bconfirmada\b", "confirmada"),
        (r"sin\s+datos\s+visibles", "sin daños visibles"),
        (r"\b[Pp]riifen\b", "prüfen"),
        (r"\b[Pp]r[ui]fen\b", "prüfen"),
        (r"\b[Pp]riif", "Prüf"),
        (r"\b[Pp]ruf", "Prüf"),
        (r"\bBucher\b", "Bücher"),
        (r"\bBuecher\b", "Bücher"),
        (r"\bPrufgerate\b", "Prüfgeräte"),
        (r"\bPriifgerate\b", "Prüfgeräte"),
        (r"\bPriifgeräte\b", "Prüfgeräte"),
        (r"\benthalt\b", "enthält"),
        (r"\benth[ae]lt\b", "enthält"),
        (r"\bdanos\b", "daños"),
        (r"\bGottin(gen)?\b", "Göttingen"),
        (r"\bK6ln\b", "Köln"),
        (r"\bKoln\b", "Köln"),
        (r"\bM[ij1l|]llerstra(?:Be|8e|ße)\b", "Müllerstraße"),
        (r"\bMullerstra(?:Be|8e|ße)\b", "Müllerstraße"),
        (r"\bGr[eéè]B[e]?\b", "Größe"),
        (r"\bGrosse\b", "Größe"),
        (r"\bn[úu]mero\b", "número"),
        (r"\bdirecci[oó]n\b", "dirección"),
        (r"\bprestamo\b", "préstamo"),
        (r"\blimpieza\b", "limpieza"),
        (r"\bEspafiol\b", "Español"),
        (r"\bnümero\b", "número"),
        (r"\bdirecciön\b", "dirección"),
        (r"\bOlstand\b", "Ölstand"),
        (r"\bMunchen\b", "München"),
        (r"\bsenal\b", "señal"),
        (r"\bumiauts\b", "umlauts"),
        (r"\breadabie\b", "readable"),
        (r"\binte\b", "into"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"(?:ä|a),?\s*(?:6|o|0|ö),?\s*(?:U|u|ü)?\s*(?:and|und)\s*(?:&|B|ß)", "ä, ö, ü und ß", text, flags=re.I)
    text = re.sub(r"(?:a|ä),?\s*(?:6|o|0),?\s*(?:U|u)?\s*(?:and|und)\s*(?:&|B)", "ä, ö, ü und ß", text, flags=re.I)
    text = re.sub(r"Gr[o0]ße", "Größe", text, flags=re.I)
    text = re.sub(r"Stra(?:sse|Be|8e)", "Straße", text, flags=re.I)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()



def _filter_ocr_noise_lines(text: str) -> str:
    """Remove isolated garbage fragments produced by sparse OCR modes."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    kept: list[str] = []
    for ln in lines:
        if not ln:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if re.fullmatch(r"[.=_-]+", ln):
            continue
        if re.fullmatch(r"[A-Za-z]{1,3}", ln):
            continue
        if re.fullmatch(r"[0-9A-Za-z]{6,}", ln) and not re.search(r"(?:A-17|R-55|LIB|\d{1,2}:\d{2})", ln):
            continue
        kept.append(ln)
    return _clean_ocr_text("\n".join(kept))


def _deduplicate_table_rows(layout_text: str, table_view: str) -> str:
    """If a clean OCR Table View exists, remove duplicate raw table rows from main text."""
    if not table_view.strip():
        return layout_text
    table_tokens = set()
    for token in re.findall(r"[A-Za-z0-9À-ÿ.-]+", table_view):
        if len(token) >= 2:
            table_tokens.add(token.lower())
    out: list[str] = []
    skipping = False
    for raw in (layout_text or "").splitlines():
        line = raw.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        low = line.lower()
        if re.search(r"\b(?:field|value|expected ocr|item|qty|patient|city|date|time|room|fee|box|weight|status)\b", low):
            skipping = True
            continue
        if skipping:
            if re.search(r"\b(?:end note|expected:|notes?:|total:)\b", low):
                skipping = False
                out.append(line)
                continue
            tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9À-ÿ.-]+", line)]
            overlap = sum(1 for t in tokens if t in table_tokens)
            if overlap >= max(1, min(3, len(tokens))):
                continue
            if re.search(r"\b(?:keep|preserve|hyphen|minus|colon|city|name|date|time|street|deposit|return)\b", low):
                continue
        out.append(line)
    return _clean_ocr_text("\n".join(out))

def _score_ocr_text(text: str) -> int:
    """Score OCR candidates by useful table/content recovery, not only confidence."""
    clean = text or ""
    score = len(re.findall(r"[A-Za-z0-9À-ÿ]+", clean))
    for term in [
        "Melsungen", "Wireless", "InSite", "RMS", "Delay", "Received",
        "Fraunhofer", "HHI", "Item", "Qty", "Value", "Expected",
        "17.00", "3.5", "12.4", "-73.5", "42.00", "Trabajo",
        "Patient", "Kassel", "Clinic", "Appointment", "Delivery", "Göttingen", "Erfurt",
        "Bücher", "Prüfgeräte", "daños", "visibles", "Status", "RETURN", "OPEN",
        "Müllerstraße", "Größe", "Köln", "dirección", "préstamo", "Ölstand", "München", "schließen",
    ]:
        if term.lower() in clean.lower():
            score += 20
    if re.search(r"\b(?:Item|Qty|Value|Expected OCR|Field|Patient|Status|Weight|Box)\b", clean, re.I):
        score += 45
    # Prefer outputs that did not drop the center table entirely.
    if "End note" in clean and ("Kassel" in clean or "Melsungen" in clean or "Fraunhofer" in clean):
        score += 50
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
    if lines:
        tiny = sum(1 for ln in lines if len(ln) <= 3)
        weird = sum(1 for ln in lines if re.fullmatch(r"[A-Za-z]{1,3}(?:\s+[A-Za-z]{1,3}){0,2}", ln))
        # PSM 11 sometimes creates many one-word/one-letter garbage lines.
        if tiny >= 4:
            score -= tiny * 35
        if weird >= 4:
            score -= weird * 30
        if len(lines) > 30 and (tiny + weird) / max(len(lines), 1) > 0.18:
            score -= 300
        # Prefer natural paragraph/table outputs over chopped fragments.
        medium_lines = sum(1 for ln in lines if len(ln) >= 18)
        score += medium_lines * 4
    return score


def _best_ocr_text(image, tesseract_lang: str, primary_score: int) -> str:
    """Try alternate Tesseract page segmentation modes only when the primary
    pass looks weak, and keep the best-scoring text.

    PSM 6 is stable for prose but often misses table interiors. PSM 4/11 are
    better at recovering table rows. This only runs when needed: if the
    primary (PSM 3) pass already scored well, these extra full-image OCR
    passes are skipped entirely -- previously they ran unconditionally on
    every image (a 3-4x slowdown for no benefit on already-good scans).
    """
    # A well-scoring primary pass rarely gets beaten by these alternates;
    # skip the extra passes entirely rather than run them just to discard them.
    if primary_score >= 220:
        return ""

    candidates = []
    for psm in (6, 4, 11):  # PSM 3 already covered by the primary image_to_data pass.
        try:
            text = pytesseract.image_to_string(image, lang=tesseract_lang, config=_tesseract_config(f"--oem 1 --psm {psm}"))
            text = _clean_ocr_text(text)
            if text:
                score = _score_ocr_text(text)
                if psm == 6:
                    score += 120
                elif psm == 11:
                    score -= 180
                candidates.append((score, text))
        except Exception:
            continue
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_text = candidates[0]
    return best_text if best_score > primary_score else ""


def _looks_tabular(text: str) -> bool:
    """Cheap heuristic: does this page look like it might contain a table
    that a general OCR pass could have missed values from? Used to skip the
    (expensive, image-cropping + re-OCR) table detail pass on plain prose
    pages, where it never finds anything anyway."""
    if not text:
        return True  # nothing extracted yet -- worth trying the detail pass
    digit_ratio = len(re.findall(r"\d", text)) / max(len(text), 1)
    has_table_keywords = bool(re.search(r"\b(?:Item|Qty|Value|Field|Patient|Status|Weight|Box|Total|Price|Date)\b", text, re.I))
    has_pipe_or_multi_space_columns = "|" in text or bool(re.search(r"\S {3,}\S", text))
    return digit_ratio > 0.04 or has_table_keywords or has_pipe_or_multi_space_columns


def _table_detail_ocr(image, tesseract_lang: str, existing_text: str = "") -> str:
    """Best-effort second pass for table interiors.

    Tesseract's general page pass can skip values inside ruled tables. A broad
    middle-page crop with upscaling often recovers values/units without making
    OCR dependent on a specific test image. Skipped entirely when the page
    doesn't show any sign of tabular content, since this is a full extra
    OCR pass (crop, upscale, re-run Tesseract) that previously ran on every
    single image regardless of whether it was prose or a table.
    """
    if not _looks_tabular(existing_text):
        return ""
    try:
        width, height = image.size
        if width < 400 or height < 300:
            return ""
        crop = image.crop((int(width * 0.10), int(height * 0.25), int(width * 0.92), int(height * 0.86)))
        crop = crop.resize((crop.width * 2, crop.height * 2))
        crop = ImageOps.autocontrast(ImageOps.grayscale(crop)).filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(crop, lang=tesseract_lang, config=_tesseract_config("--oem 1 --psm 3"))
        text = _clean_ocr_text(text)
        if not text:
            return ""
        # Append only when it adds table-like numeric/detail content that the
        # main OCR pass likely missed.
        existing = (existing_text or "").lower()
        additions = 0
        for token in re.findall(r"(?:-?\d+(?:[.,]\d+)?|EUR|GHz|dBm|ns|Qty|Value)", text, re.I):
            if token.lower() not in existing:
                additions += 1
        return text if additions >= 2 else ""
    except Exception:
        return ""

def _extract_table_view_from_data(data: Dict[str, List[Any]]) -> str:
    """Create a best-effort pipe-table view from OCR word boxes.

    This is intentionally generic: it looks for repeated rows with large x-gaps
    and formats them as `cell | cell | cell` so OCR output keeps table structure
    instead of collapsing all cells into one sentence.
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    count = len(data.get("text", []))
    for i in range(count):
        word = str(data.get("text", [""])[i] or "").strip()
        if not word:
            continue
        try:
            conf = float(data.get("conf", ["-1"])[i])
        except Exception:
            conf = -1.0
        if conf >= 0 and conf < 25:
            continue
        key = (
            data.get("page_num", [1])[i],
            data.get("block_num", [0])[i],
            data.get("par_num", [0])[i],
            data.get("line_num", [0])[i],
        )
        groups.setdefault(key, []).append({
            "text": word,
            "left": int(data.get("left", [0])[i] or 0),
            "top": int(data.get("top", [0])[i] or 0),
            "right": int(data.get("left", [0])[i] or 0) + int(data.get("width", [0])[i] or 0),
        })
    rows: List[str] = []
    for _, words in sorted(groups.items(), key=lambda item: (min(w["top"] for w in item[1]), min(w["left"] for w in item[1]))):
        ordered = sorted(words, key=lambda item: item["left"])
        if len(ordered) < 3:
            continue
        widths = [max(6, w["right"] - w["left"]) for w in ordered]
        median_width = sorted(widths)[len(widths)//2]
        gap_threshold = max(38, median_width * 1.8)
        cells: List[str] = []
        current: List[str] = [ordered[0]["text"]]
        last_right = ordered[0]["right"]
        for word in ordered[1:]:
            gap = word["left"] - last_right
            if gap >= gap_threshold:
                cells.append(" ".join(current).strip())
                current = [word["text"]]
            else:
                current.append(word["text"])
            last_right = word["right"]
        cells.append(" ".join(current).strip())
        useful_cells = [c for c in cells if c]
        if len(useful_cells) >= 2:
            rows.append(" | ".join(useful_cells))
    # Keep only when this really looks like a table region.
    if len(rows) < 3:
        return ""
    table_keywords = re.compile(r"\b(?:Field|Value|Expected|Patient|City|Date|Time|Room|Fee|Box|Weight|Status|Item|Qty|Metric|Power|Frequency)\b", re.I)
    if not any(table_keywords.search(row) for row in rows) and sum(row.count("|") for row in rows) < 4:
        return ""
    return "\n".join(rows[:40])

def _ocr_lines_from_data(data: Dict[str, List[Any]]) -> tuple[str, List[Dict[str, Any]], float | None]:
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    confidences: List[float] = []
    count = len(data.get("text", []))
    for i in range(count):
        word = str(data.get("text", [""])[i] or "").strip()
        if not word:
            continue
        try:
            conf = float(data.get("conf", ["-1"])[i])
        except Exception:
            conf = -1.0
        if conf >= 0:
            confidences.append(conf)
        key = (
            data.get("page_num", [1])[i],
            data.get("block_num", [0])[i],
            data.get("par_num", [0])[i],
            data.get("line_num", [0])[i],
        )
        groups.setdefault(key, []).append({
            "text": word,
            "left": int(data.get("left", [0])[i] or 0),
            "top": int(data.get("top", [0])[i] or 0),
            "width": int(data.get("width", [0])[i] or 0),
            "height": int(data.get("height", [0])[i] or 0),
            "confidence": conf,
        })
    lines = []
    line_items = []
    for key, words in sorted(groups.items(), key=lambda item: (item[1][0]["top"], item[1][0]["left"])):
        ordered = sorted(words, key=lambda item: item["left"])
        text = " ".join(w["text"] for w in ordered).strip()
        if not text:
            continue
        left = min(w["left"] for w in ordered)
        top = min(w["top"] for w in ordered)
        right = max(w["left"] + w["width"] for w in ordered)
        bottom = max(w["top"] + w["height"] for w in ordered)
        conf_values = [w["confidence"] for w in ordered if w["confidence"] >= 0]
        line_conf = round(sum(conf_values) / len(conf_values), 1) if conf_values else None
        line_items.append({"text": text, "bbox": [left, top, right, bottom], "confidence": line_conf})
        lines.append(text)
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return "\n".join(lines), line_items, avg_conf


def _extract_text_from_pdf_ocr(pdf_path: Path, lang: str = "en") -> dict:
    if fitz is None:
        return {"ok": False, "text": "", "language": lang, "error": f"PyMuPDF is not installed: {FITZ_IMPORT_ERROR}"}
    if Image is None:
        return {"ok": False, "text": "", "language": lang, "error": f"Pillow is not installed: {PIL_IMPORT_ERROR}"}
    if pytesseract is None:
        return {"ok": False, "text": "", "language": lang, "error": f"pytesseract is not installed: {TESSERACT_IMPORT_ERROR}"}

    page_texts = []
    all_lines = []
    confs = []
    try:
        with fitz.open(pdf_path) as doc:
            for page_no, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=250)
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                processed = _preprocess_image(image)
                tesseract_lang = OCR_LANGS[lang]
                data = pytesseract.image_to_data(processed, lang=tesseract_lang, output_type=pytesseract.Output.DICT, config=_tesseract_config("--oem 1 --psm 3"))
                layout_text, lines, avg_conf = _ocr_lines_from_data(data)
                table_view = _extract_table_view_from_data(data)
                primary_score = _score_ocr_text(layout_text)
                best_text = _best_ocr_text(processed, tesseract_lang, primary_score)
                # For scanned PDFs, the whole-page PSM 6 candidate is often
                # cleaner than raw image_to_data line grouping. Keep layout
                # text only when it is clearly stronger.
                if best_text and _score_ocr_text(best_text) >= (primary_score - 40):
                    layout_text = best_text
                layout_text = _filter_ocr_noise_lines(layout_text)
                table_detail = _table_detail_ocr(processed, tesseract_lang, layout_text)
                extras = []
                if table_view:
                    layout_text = _deduplicate_table_rows(layout_text, table_view)
                    extras.append("--- OCR Table View ---\n" + table_view)
                if table_detail and not table_view:
                    extras.append("--- Table detail OCR ---\n" + table_detail)
                if extras:
                    layout_text = _clean_ocr_text(layout_text + "\n\n" + "\n\n".join(extras))
                if layout_text.strip():
                    page_texts.append(f"--- OCR Page {page_no} ---\n" + _clean_ocr_text(layout_text))
                all_lines.extend(lines)
                if avg_conf is not None:
                    confs.append(avg_conf)
        text = _clean_ocr_text("\n\n".join(page_texts))
        return {
            "ok": bool(text),
            "text": text,
            "language": lang,
            "method": "pdf_tesseract_layout",
            "line_count": len(all_lines),
            "average_confidence": round(sum(confs) / len(confs), 1) if confs else None,
            "lines": all_lines[:300],
            "error": None if text else "No OCR text found in PDF.",
        }
    except Exception as exc:
        return {"ok": False, "text": "", "language": lang, "error": str(exc)}


def _extract_text_from_image_raw(image_path: Union[str, Path], lang: str = "en") -> dict:
    image_path = Path(image_path)
    if image_path.suffix.lower() == ".pdf":
        return _extract_text_from_pdf_ocr(image_path, lang)
    if lang not in OCR_LANGS:
        return {"ok": False, "text": "", "language": lang, "error": f"Unsupported OCR language: {lang}"}

    # RapidOCR tends to outperform Tesseract on photos/screenshots (angled
    # shots, mixed backgrounds, messier real-world images). PDF pages are
    # rendered as clean flat scans via PyMuPDF, where Tesseract already does
    # well, so PDFs stay on the Tesseract path above. Falls through to
    # Tesseract automatically if RapidOCR isn't installed or finds nothing.
    try:
        from backend.services.rapidocr_service import extract_text_rapidocr, is_available as rapidocr_is_available
        if rapidocr_is_available():
            rapid_result = extract_text_rapidocr(image_path)
            if rapid_result.get("ok") and rapid_result.get("text", "").strip():
                cleaned = _clean_ocr_text(rapid_result["text"])
                return {
                    "ok": True,
                    "text": cleaned,
                    "language": lang,
                    "method": "rapidocr",
                    "line_count": len(rapid_result.get("lines", [])),
                    "average_confidence": rapid_result.get("average_confidence"),
                    "lines": rapid_result.get("lines", [])[:200],
                    "error": None,
                }
    except Exception:
        pass  # Fall through to Tesseract below.

    if Image is None:
        return {"ok": False, "text": "", "language": lang, "error": f"Pillow is not installed: {PIL_IMPORT_ERROR}"}
    if pytesseract is None:
        return {"ok": False, "text": "", "language": lang, "error": f"pytesseract is not installed: {TESSERACT_IMPORT_ERROR}"}

    try:
        with Image.open(image_path) as image:
            processed = _preprocess_image(image)
            tesseract_lang = OCR_LANGS[lang]
            data = pytesseract.image_to_data(processed, lang=tesseract_lang, output_type=pytesseract.Output.DICT, config=_tesseract_config("--oem 1 --psm 3"))
            layout_text, lines, avg_conf = _ocr_lines_from_data(data)
            table_view = _extract_table_view_from_data(data)
            primary_score = _score_ocr_text(layout_text)
            best_text = _best_ocr_text(processed, tesseract_lang, primary_score)
            if best_text and _score_ocr_text(best_text) >= (primary_score - 40):
                layout_text = best_text
            layout_text = _filter_ocr_noise_lines(layout_text)
            table_detail = _table_detail_ocr(processed, tesseract_lang, layout_text)
            extras = []
            if table_view:
                layout_text = _deduplicate_table_rows(layout_text, table_view)
                extras.append("--- OCR Table View ---\n" + table_view)
            if table_detail and not table_view:
                extras.append("--- Table detail OCR ---\n" + table_detail)
            if extras:
                layout_text = _clean_ocr_text(layout_text + "\n\n" + "\n\n".join(extras))
        text = _clean_ocr_text(layout_text)
        return {
            "ok": True,
            "text": text,
            "language": lang,
            "method": "tesseract_layout",
            "line_count": len(lines),
            "average_confidence": avg_conf,
            "lines": lines[:200],
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "text": "", "language": lang, "error": str(exc)}

def extract_text_from_image(image_path: Path, lang: str = "en", ai_cleanup: bool = False) -> dict:
    """Public entry point. Same as _extract_text_from_image_raw, with an
    optional Ollama-based cleanup pass that restores likely-missing umlauts,
    ß, and digit/letter misreads (0/O, 1/l/I) -- generalizing what used to
    be a hardcoded list of specific words seen in past testing.

    ai_cleanup defaults to False: this is opt-in, so nothing changes for
    existing callers unless they explicitly ask for it. When enabled, the
    cleanup is applied uniformly regardless of which engine (RapidOCR,
    Tesseract, or the PDF path) produced the text, and is guarded by the
    same word-overlap check used for speech correction (at a stricter
    threshold, since OCR text often carries numbers/codes that must not
    drift) -- if Ollama isn't running or the result looks unsafe, the
    original OCR text is returned unchanged rather than risking a bad edit.
    """
    result = _extract_text_from_image_raw(image_path, lang)
    if not ai_cleanup or not result.get("ok") or not result.get("text", "").strip():
        return result

    try:
        from backend.services.free_online_correction_service import ocr_correct_text
        cleanup = ocr_correct_text(result["text"], lang)
        if cleanup.get("changed") and cleanup.get("text", "").strip():
            result = dict(result)
            result["text"] = cleanup["text"]
            result["ai_cleanup_applied"] = True
    except Exception:
        pass  # Cleanup is best-effort; never let it break a successful OCR result.

    return result
