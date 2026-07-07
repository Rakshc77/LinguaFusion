from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse

from backend.config.paths import TEMP_DIR, ensure_runtime_dirs, read_version
from backend.config.runtime import runtime_health
from backend.services.ai_provider_config_service import (
    public_ai_provider_config,
    save_ai_provider_config,
    test_provider,
)
from backend.services.correction_service import apply_corrections, load_corrections, add_correction
from backend.services.document_translation_service import translate_document_preserving_format
from backend.services.file_reader_service import extract_text_from_file
from backend.services.document_intelligence_service import analyze_document, export_reader_document, normalize_document_text
from backend.services.free_online_correction_service import provider_status, smart_correct_text
from backend.services.language_service import detect_text_language
from backend.services.notes_service import create_note, list_notes, get_note, delete_note
from backend.services.ocr_service import extract_text_from_image
from backend.services.piper_service import speak_to_file
from backend.services.reference_lyrics_service import reference_assisted_lyrics
from backend.services.speech_engine_v2 import transcribe_speech_engine_v2
from backend.services.translation_service import translate_with_views
from backend.services.whisper_service import transcribe_audio

ensure_runtime_dirs()

APP_VERSION = read_version()

app = FastAPI(
    title="LinguaFusion",
    description="Offline-first speech, translation, reader, notes and OCR assistant.",
    version=APP_VERSION,
)


def api_error(stage: str, exc: Exception | str, status_code: int = 200, **extra: Any) -> JSONResponse | Dict[str, Any]:
    payload = {
        "ok": False,
        "stage": stage,
        "error": str(exc),
        **extra,
    }
    if status_code == 200:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


def save_upload(upload_file: UploadFile) -> Path:
    ensure_runtime_dirs()
    filename = upload_file.filename or "upload.bin"
    suffix = Path(filename).suffix.lower() or ".bin"
    if len(suffix) > 12:
        suffix = ".bin"
    path = TEMP_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
    with open(path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return path


def convert_to_wav(input_path: Path) -> Path:
    output_path = TEMP_DIR / f"audio_{uuid.uuid4().hex}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg was not found. Install ffmpeg or add it to PATH before using speech/audio features.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or "Audio conversion failed.").strip()) from exc
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Audio conversion did not create a valid WAV file.")
    return output_path


@app.get("/", tags=["System"])
def root():
    return {
        "ok": True,
        "app": "LinguaFusion",
        "version": APP_VERSION,
        "status": "running",
        "modes": ["translate", "reader", "speech", "ocr", "notes", "settings"],
    }


@app.get("/health", tags=["System"])
def health_check():
    return runtime_health()


@app.get("/diagnostics", tags=["System"])
def diagnostics():
    return runtime_health()


@app.post("/stt/transcribe", tags=["Speech"])
async def stt_transcribe(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    smart_mode: str = Form("offline"),
):
    try:
        uploaded_path = save_upload(file)
        wav_path = convert_to_wav(uploaded_path)
        return transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=False)
    except Exception as exc:
        return api_error("speech_transcription", exc, text="", language=language)


@app.post("/stt/full-song-pass", tags=["Speech"])
async def stt_full_song_pass(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    smart_mode: str = Form("free_auto"),
):
    try:
        uploaded_path = save_upload(file)
        wav_path = convert_to_wav(uploaded_path)
        return transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=True)
    except Exception as exc:
        return api_error("song_transcription", exc, text="", language=language)


@app.post("/stt/reference-lyrics-pass", tags=["Speech"])
async def stt_reference_lyrics_pass(
    file: UploadFile = File(...),
    reference_lyrics: str = Form(...),
    language: str = Form("auto"),
    smart_mode: str = Form("free_auto"),
):
    try:
        uploaded_path = save_upload(file)
        wav_path = convert_to_wav(uploaded_path)
        base = transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=True)
        aligned = reference_assisted_lyrics(base.get("text", ""), reference_lyrics)
        aligned.update({
            "language": base.get("language", "en"),
            "model": base.get("model"),
            "base_provider": base.get("provider"),
            "base_engine": base.get("engine"),
            "chunk_count": base.get("chunk_count"),
            "provider_status": base.get("provider_status"),
        })
        return aligned
    except Exception as exc:
        return api_error("reference_lyrics_pass", exc, text="", language=language)


@app.get("/corrections", tags=["Speech"])
def corrections_list():
    return {"ok": True, "corrections": load_corrections()}


@app.post("/corrections/add", tags=["Speech"])
async def corrections_add(wrong: str = Form(...), correct: str = Form(...)):
    try:
        return {"ok": True, "corrections": add_correction(wrong, correct)}
    except Exception as exc:
        return api_error("corrections_add", exc)


@app.post("/corrections/apply", tags=["Speech"])
async def corrections_apply(text: str = Form(...)):
    return {"ok": True, "text": apply_corrections(text)}


@app.get("/corrections/providers", tags=["Speech"])
def corrections_providers():
    return provider_status()


@app.post("/corrections/smart", tags=["Speech"])
async def corrections_smart(text: str = Form(...), mode: str = Form("free_auto"), language: str = Form("auto")):
    try:
        return smart_correct_text(text, mode, language)
    except Exception as exc:
        return {"ok": False, "text": text, "provider": "error", "error": str(exc)}


@app.get("/ai/providers/config", tags=["Speech"])
def ai_provider_config_get():
    return public_ai_provider_config()


@app.post("/ai/providers/config", tags=["Speech"])
async def ai_provider_config_save(
    smart_mode_enabled: bool = Form(False),
    default_mode: str = Form("free_auto"),
    primary_provider: str = Form("gemini"),
    gemini_key: str = Form(""),
    groq_key: str = Form(""),
    openrouter_key: str = Form(""),
):
    save_ai_provider_config({
        "smart_mode_enabled": smart_mode_enabled,
        "default_mode": default_mode,
        "primary_provider": primary_provider,
        "keys": {"gemini": gemini_key, "groq": groq_key, "openrouter": openrouter_key},
    })
    public = public_ai_provider_config()
    public["saved"] = True
    return public


@app.post("/ai/providers/test", tags=["Speech"])
async def ai_provider_test(provider: str = Form(...)):
    return test_provider(provider)


@app.post("/translate", tags=["Translation"])
async def translate_only(text: str = Form(...), source_lang: str = Form(...), target_lang: str = Form(...)):
    try:
        return translate_with_views(text, source_lang, target_lang)
    except Exception as exc:
        return api_error("translation", exc, translated_text="", route=[], views=None)


@app.post("/translate/document", tags=["Translation"])
async def translate_document(file: UploadFile = File(...), source_lang: str = Form("auto"), target_lang: str = Form("de")):
    try:
        uploaded_path = save_upload(file)
        extracted = extract_text_from_file(uploaded_path, source_lang)
        if not extracted.get("ok"):
            return api_error("file_import", extracted.get("error", "File import failed."))

        text = extracted.get("text", "")
        if source_lang == "auto":
            detected = detect_text_language(text)
            if not detected.get("ok"):
                return api_error("language_detection", detected.get("error", "Language detection failed."))
            resolved_source_lang = "auto" if detected.get("is_mixed") else detected.get("language")
        else:
            resolved_source_lang = source_lang
            detected = {"ok": True, "language": source_lang, "confidence": 1.0, "error": None}

        translation = translate_with_views(text, resolved_source_lang, target_lang)
        return {
            "ok": translation.get("ok"),
            "file_type": extracted.get("file_type"),
            "method": extracted.get("method"),
            "source_lang": resolved_source_lang,
            "target_lang": target_lang,
            "detected_language": detected,
            "original_text": text,
            "translation": translation,
        }
    except Exception as exc:
        return api_error("document_translation", exc)


@app.post("/translate/document/export", tags=["Translation"])
async def translate_document_export(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("de"),
    output_format: str = Form("docx"),
):
    try:
        uploaded_path = save_upload(file)
        exported_path = translate_document_preserving_format(uploaded_path, source_lang, target_lang, output_format)
        suffix = "." + output_format.lower().strip().lstrip(".")
        filename = f"{Path(file.filename or 'document').stem}_translated{suffix}"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if suffix == ".docx" else ("application/pdf" if suffix == ".pdf" else "text/plain")
        return FileResponse(exported_path, media_type=media_type, filename=filename)
    except Exception as exc:
        return api_error("format_preserving_export", exc)


@app.post("/tts/speak", tags=["TTS"])
async def tts_speak(text: str = Form(...), lang: str = Form("en"), speed: float = Form(1.0)):
    try:
        speech_path = speak_to_file(text, lang, f"tts_{uuid.uuid4().hex}.wav", speed=speed)
        return FileResponse(speech_path, media_type="audio/wav", filename="speech.wav")
    except Exception as exc:
        return api_error("tts", exc, status_code=500)


@app.post("/interpreter/full", tags=["Interpreter"])
async def interpreter_full(file: UploadFile = File(...), source_lang: str = Form("auto"), target_lang: str = Form("de")):
    try:
        uploaded_path = save_upload(file)
        wav_path = convert_to_wav(uploaded_path)
        stt_result = transcribe_speech_engine_v2(wav_path, language=source_lang, smart_mode="offline", music_mode=False)
        if not stt_result.get("ok"):
            return api_error("stt", stt_result.get("error", "Speech transcription failed."))

        detected_text = stt_result.get("text", "")
        translation_source = stt_result.get("language") or ("en" if source_lang == "auto" else source_lang)
        if translation_source == "auto":
            translation_source = "en"
        translation_result = translate_with_views(detected_text, translation_source, target_lang)
        if not translation_result.get("ok"):
            return api_error("translation", translation_result.get("error", "Translation failed."), original_text=detected_text)

        return {"ok": True, "original_text": detected_text, "target_lang": target_lang, "translation": translation_result}
    except Exception as exc:
        return api_error("interpreter", exc)


@app.post("/notes/create", tags=["Notes"])
async def notes_create(title: str = Form(...), content: str = Form(...), language: str = Form("en")):
    try:
        return create_note(title, content, language)
    except Exception as exc:
        return api_error("notes_create", exc)


@app.get("/notes", tags=["Notes"])
def notes_list():
    try:
        return list_notes()
    except Exception as exc:
        return api_error("notes_list", exc)


@app.get("/notes/{note_id}", tags=["Notes"])
def notes_get(note_id: int):
    try:
        note = get_note(note_id)
        return {"ok": bool(note), "note": note, "error": None if note else "Note not found"}
    except Exception as exc:
        return api_error("notes_get", exc)


@app.delete("/notes/{note_id}", tags=["Notes"])
def notes_delete(note_id: int):
    try:
        deleted = delete_note(note_id)
        return {"ok": deleted, "deleted": deleted}
    except Exception as exc:
        return api_error("notes_delete", exc)


@app.post("/ocr/extract", tags=["OCR"])
async def ocr_extract(file: UploadFile = File(...), lang: str = Form("en")):
    try:
        uploaded_path = save_upload(file)
        return extract_text_from_image(uploaded_path, lang)
    except Exception as exc:
        return api_error("ocr", exc, text="", language=lang)


@app.post("/image/translate", tags=["OCR"])
async def image_translate(file: UploadFile = File(...), source_lang: str = Form("en"), target_lang: str = Form("de")):
    try:
        uploaded_path = save_upload(file)
        ocr_result = extract_text_from_image(uploaded_path, source_lang)
        if not ocr_result.get("ok"):
            return api_error("ocr", ocr_result.get("error", "OCR failed."))
        extracted_text = ocr_result.get("text", "")
        translation_result = translate_with_views(extracted_text, source_lang, target_lang)
        if not translation_result.get("ok"):
            return api_error("translation", translation_result.get("error", "Translation failed."), extracted_text=extracted_text)
        return {"ok": True, "extracted_text": extracted_text, "translation": translation_result}
    except Exception as exc:
        return api_error("image_translate", exc)


@app.post("/reader/import", tags=["Reader"])
async def reader_import(file: UploadFile = File(...), lang: str = Form("auto")):
    try:
        uploaded_path = save_upload(file)
        result = extract_text_from_file(uploaded_path, lang)
        if not result.get("ok"):
            return result
        raw_text = result.get("text", "")
        text = normalize_document_text(raw_text)
        detected_language = detect_text_language(text)
        analysis = analyze_document(text)
        return {
            "ok": True,
            "file_type": result.get("file_type"),
            "method": result.get("method"),
            "detected_language": detected_language,
            "analysis": analysis,
            "text": text,
        }
    except Exception as exc:
        return api_error("reader_import", exc, text="")


@app.post("/reader/analyze", tags=["Reader"])
async def reader_analyze(text: str = Form(...)):
    try:
        return analyze_document(text)
    except Exception as exc:
        return api_error("reader_analyze", exc)


@app.post("/reader/export", tags=["Reader"])
async def reader_export(text: str = Form(...), output_format: str = Form("txt"), title: str = Form("LinguaFusion Reader Export")):
    try:
        exported_path = export_reader_document(text, output_format, title=title)
        suffix = "." + output_format.lower().strip().lstrip(".")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if suffix == ".docx" else ("application/pdf" if suffix == ".pdf" else "text/plain")
        return FileResponse(exported_path, media_type=media_type, filename=f"reader_export{suffix}")
    except Exception as exc:
        return api_error("reader_export", exc)


@app.post("/reader/speak", tags=["Reader"])
async def reader_speak(text: str = Form(...), lang: str = Form("en"), speed: float = Form(1.0)):
    try:
        speech_path = speak_to_file(text, lang, f"reader_{uuid.uuid4().hex}.wav", speed=speed)
        return FileResponse(speech_path, media_type="audio/wav", filename="reader_output.wav")
    except Exception as exc:
        return api_error("reader_speak", exc, status_code=500)


@app.post("/reader/translate", tags=["Reader"])
async def reader_translate(text: str = Form(...), target_lang: str = Form("de"), source_lang: str = Form("auto")):
    try:
        resolved_source = source_lang
        if source_lang == "auto":
            detected = detect_text_language(text)
            if not detected.get("ok"):
                return api_error("language_detection", detected.get("error", "Language detection failed."))
            if detected.get("is_mixed"):
                resolved_source = "auto"
            else:
                resolved_source = detected.get("language")
                if resolved_source not in {"en", "de", "es", "hi"}:
                    resolved_source = "en"
        translation = translate_with_views(text, resolved_source, target_lang)
        return {"ok": translation.get("ok"), "source_lang": resolved_source, "target_lang": target_lang, "translation": translation}
    except Exception as exc:
        return api_error("reader_translate", exc)


@app.post("/language/detect", tags=["Language"])
async def language_detect(text: str = Form(...)):
    try:
        return detect_text_language(text)
    except Exception as exc:
        return api_error("language_detection", exc)
