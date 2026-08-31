"""
Tests for ollama_client.py — retry-with-correction loop behavior.

All Ollama HTTP calls are mocked: no network, no local model needed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import ollama_client  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _install_responses(monkeypatch, payloads):
    """Make ollama_client.requests.post return each payload in turn."""
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        return FakeResponse({"response": payloads[len(calls) - 1]})

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    return calls


def test_generate_returns_raw_response(monkeypatch):
    calls = _install_responses(monkeypatch, ["hello world"])
    result = ollama_client.generate("say hi", temperature=0.1)
    assert result == "hello world"
    assert calls[0]["model"] == config.OLLAMA_MODEL
    assert calls[0]["stream"] is False
    assert calls[0]["options"]["temperature"] == 0.1


def test_validated_success_first_try(monkeypatch):
    _install_responses(monkeypatch, ["[1, 2, 3]"])

    def validator(raw):
        assert raw.strip().startswith("[")
        return [1, 2, 3]

    result = ollama_client.generate_validated("prompt", validator)
    assert result == [1, 2, 3]


def test_validated_retries_then_succeeds(monkeypatch):
    _install_responses(
        monkeypatch,
        [
            "Sure! Here is the answer: [1, 2",  # invalid JSON
            "[1, 2, 3]",  # corrected
        ],
    )
    attempts = []

    def validator(raw):
        import json

        attempts.append(raw)
        return json.loads(raw)  # raises ValueError subclass on bad JSON

    result = ollama_client.generate_validated("prompt", validator)
    assert result == [1, 2, 3]
    assert len(attempts) == 2
    # The retry prompt must contain the rejected answer and the reason,
    # so the model can actually correct itself.
    # (checked indirectly: two calls happened; prompt content asserted
    # in the concept_segmenter tests via fake_post capture)


def test_validated_gives_up_after_max_attempts(monkeypatch):
    payloads = ["garbage"] * (1 + config.OLLAMA_MAX_REPAIR_ATTEMPTS)
    _install_responses(monkeypatch, payloads)

    def validator(raw):
        raise ValueError("not valid JSON")

    with pytest.raises(ValueError, match="not valid JSON"):
        ollama_client.generate_validated("prompt", validator)


def test_validated_retry_prompt_contains_rejected_output(monkeypatch):
    calls = _install_responses(
        monkeypatch,
        [
            "bad answer {",
            "good answer",
        ],
    )

    def validator(raw):
        if "bad" in raw:
            raise ValueError("was bad")
        return "ok"

    ollama_client.generate_validated("original prompt", validator)
    assert len(calls) == 2
    retry_prompt = calls[1]["prompt"]
    assert "original prompt" in retry_prompt
    assert "bad answer {" in retry_prompt
    assert "was bad" in retry_prompt


def test_validated_on_retry_hook_called(monkeypatch):
    _install_responses(monkeypatch, ["bad", "good"])
    seen = []

    def validator(raw):
        if raw == "bad":
            raise ValueError("nope")
        return "good"

    ollama_client.generate_validated(
        "p", validator, on_retry=lambda attempt, reason: seen.append((attempt, reason))
    )
    assert seen == [(1, "nope")]
