from __future__ import annotations

import json

import pytest

from backend.services import agent_planner_service as planner


def _config():
    return {
        "enabled": True,
        "url": "http://127.0.0.1:11434",
        "planner_model": "test-planner",
        "model": "test-planner",
        "num_gpu": 999,
        "keep_alive": -1,
    }


def _translation_note_proposal():
    return {
        "title": "Translate and save",
        "summary": "Translate the supplied text to German, then save the result.",
        "can_execute": True,
        "steps": [
            {
                "tool": "translate_text",
                "input": {"text": "Hello", "source_lang": "en", "target_lang": "de"},
                "max_attempts": 2,
            },
            {
                "tool": "create_note",
                "input": {
                    "title": "German greeting",
                    "content": "$step.0.translated_text",
                    "language": "de",
                },
                "max_attempts": 1,
            },
        ],
        "time_budget_seconds": 300,
        "warnings": ["Saving the note requires PC-owner approval."],
    }


def test_planner_returns_validated_preview_and_permissions(monkeypatch):
    monkeypatch.setattr(planner, "_planner_config", _config)
    monkeypatch.setattr(
        planner, "_call_ollama", lambda messages, schema, config: json.dumps(_translation_note_proposal())
    )

    result = planner.plan_task("Translate Hello to German and save it as a note")

    assert result["can_execute"] is True
    assert result["model"] == "test-planner"
    assert result["repaired"] is False
    assert [step["tool"] for step in result["steps"]] == ["translate_text", "create_note"]
    assert result["approval_required"] == ["local_write"]
    assert result["automatic_permissions"] == ["local_processing"]
    assert all("permission" not in step for step in result["steps"])


def test_planner_performs_one_safe_repair(monkeypatch):
    monkeypatch.setattr(planner, "_planner_config", _config)
    responses = iter(["{not-json", json.dumps(_translation_note_proposal())])
    calls = []

    def fake_call(messages, schema, config):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(planner, "_call_ollama", fake_call)
    result = planner.plan_task("Translate Hello to German and save it")

    assert result["repaired"] is True
    assert len(calls) == 2
    assert "failed validation" in calls[1][-1]["content"]


def test_planner_rejects_disabled_tools_even_after_repair(monkeypatch):
    monkeypatch.setattr(planner, "_planner_config", _config)
    unsafe = _translation_note_proposal()
    unsafe["steps"] = [{"tool": "shell", "input": {"command": "whoami"}}]
    monkeypatch.setattr(
        planner, "_call_ollama", lambda messages, schema, config: json.dumps(unsafe)
    )

    with pytest.raises(ValueError, match="Unknown or disabled tool"):
        planner.plan_task("Run whoami")


def test_planner_can_decline_unsupported_request(monkeypatch):
    monkeypatch.setattr(planner, "_planner_config", _config)
    declined = {
        "title": "Unsupported request",
        "summary": "LinguaFusion cannot send email because external tools are disabled.",
        "can_execute": False,
        "steps": [],
        "time_budget_seconds": 60,
        "warnings": [],
    }
    monkeypatch.setattr(
        planner, "_call_ollama", lambda messages, schema, config: json.dumps(declined)
    )

    result = planner.plan_task("Email this translation")

    assert result["can_execute"] is False
    assert result["steps"] == []
    assert result["required_permissions"] == []


def test_preview_rejects_forward_references():
    proposal = _translation_note_proposal()
    proposal["steps"][0]["input"]["text"] = "$step.1.text"
    raw = json.dumps(proposal)
    with pytest.raises(ValueError, match="earlier step"):
        planner._validate_proposal(raw, "Translate and save")
