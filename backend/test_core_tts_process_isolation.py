"""Regression checks for crash-safe Piper synthesis."""

from pathlib import Path

from backend.services import piper_service


def test_piper_uses_an_isolated_process_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("LF_PIPER_IN_PROCESS", raising=False)
    monkeypatch.setattr(piper_service, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(piper_service, "MODELS_DIR", piper_service.PIPER_MODELS_DIR)

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output_index = command.index("--output-file") + 1
        Path(command[output_index]).write_bytes(b"RIFF" + b"\x00" * 64)

    monkeypatch.setattr(piper_service.subprocess, "run", fake_run)

    output = piper_service._speak_single_voice_to_file(
        "Crash-safe speech synthesis.", "en", "isolated.wav", 1.0
    )

    assert output.read_bytes().startswith(b"RIFF")
    assert len(calls) == 1
    command, options = calls[0]
    assert command[1:3] == ["-m", "piper"]
    assert options["check"] is True
    assert options["capture_output"] is True


def test_frozen_piper_uses_packaged_worker(monkeypatch, tmp_path):
    monkeypatch.delenv("LF_PIPER_IN_PROCESS", raising=False)
    monkeypatch.setattr(piper_service, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(piper_service, "MODELS_DIR", piper_service.PIPER_MODELS_DIR)
    monkeypatch.setattr(piper_service.sys, "frozen", True, raising=False)
    monkeypatch.setattr(piper_service.sys, "executable", r"C:\Apps\LinguaFusion.exe")

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output_index = command.index("--output-file") + 1
        Path(command[output_index]).write_bytes(b"RIFF" + b"\x00" * 64)

    monkeypatch.setattr(piper_service.subprocess, "run", fake_run)

    output = piper_service._speak_single_voice_to_file(
        "Packaged speech synthesis.", "en", "packaged.wav", 1.0
    )

    assert output.read_bytes().startswith(b"RIFF")
    command, options = calls[0]
    assert command[:2] == [r"C:\Apps\LinguaFusion.exe", "--piper-worker"]
    assert "-m" not in command
    assert options["creationflags"] == getattr(piper_service.subprocess, "CREATE_NO_WINDOW", 0)
