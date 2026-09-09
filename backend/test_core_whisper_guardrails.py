from backend.services.whisper_service import _is_hotword_only_hallucination


def test_long_recording_rejects_implausible_hotword_only_segment():
    assert _is_hotword_only_hallucination(
        "LinguaFusion",
        [{"start": 2.06, "end": 2.14, "text": "LinguaFusion"}],
        96.67,
    ) is True


def test_short_or_substantive_hotword_transcript_is_not_rejected():
    assert _is_hotword_only_hallucination(
        "LinguaFusion",
        [{"start": 0.0, "end": 0.8, "text": "LinguaFusion"}],
        1.0,
    ) is False
    assert _is_hotword_only_hallucination(
        "Welcome to LinguaFusion",
        [{"start": 0.0, "end": 1.5, "text": "Welcome to LinguaFusion"}],
        10.0,
    ) is False
