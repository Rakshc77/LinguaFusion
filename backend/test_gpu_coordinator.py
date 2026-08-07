from __future__ import annotations

import threading
import time


def test_exclusive_gpu_job_releases_idle_models(monkeypatch):
    import backend.services.gpu_coordinator as coordinator

    released: list[str] = []
    monkeypatch.setattr(coordinator, "_release_idle_models", released.append)

    with coordinator.gpu_operation("odia_asr", exclusive=True):
        pass
    with coordinator.gpu_operation("whisper"):
        pass

    assert released == ["odia_asr"]


def test_whisper_model_can_be_released_for_vram_handover(monkeypatch):
    import backend.services.whisper_service as whisper

    monkeypatch.setattr(whisper, "_model", object())
    monkeypatch.setattr(whisper, "_model_desc", "loaded test model")

    whisper.release_model()

    assert whisper._model is None
    assert whisper._model_desc == ""


def test_gpu_jobs_are_serialized_between_friend_requests():
    import backend.services.gpu_coordinator as coordinator

    guard = threading.Lock()
    active = 0
    peak = 0

    def run_job() -> None:
        nonlocal active, peak
        with coordinator.gpu_operation("test"):
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with guard:
                active -= 1

    workers = [threading.Thread(target=run_job) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)

    assert not any(worker.is_alive() for worker in workers)
    assert peak == 1
