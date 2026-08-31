"""
Tests for concept_segmenter.py — heuristic mode, JSON extraction,
mocked Ollama runs (success / retry / fallback).

No network access: Ollama POSTs are monkeypatched.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import concept_segmenter  # noqa: E402
import ollama_client  # noqa: E402


def make_word(word, start, end):
    return {"word": word, "start": start, "end": end, "confidence": 0.95}


# ---------------------------------------------------------------------------
# Heuristic mode (deterministic, no LLM)
# ---------------------------------------------------------------------------

def test_heuristic_splits_on_pauses(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "heuristic")
    monkeypatch.setattr(config, "HEURISTIC_PAUSE_GAP_SECONDS", 0.45)
    monkeypatch.setattr(config, "HEURISTIC_MIN_SEGMENT_WORDS", 6)

    words = (
        [make_word("a", i * 0.3, i * 0.3 + 0.2) for i in range(8)]  # concept 1
        + [make_word("b", 10.0, 10.2)]                              # pause before this
        + [make_word("c", 10.3, 10.5) for _ in range(8)]            # concept 2
    )
    segments = concept_segmenter.segment_dd_block(words)
    assert len(segments) == 2
    assert segments[0].start == 0.0
    assert segments[1].start == 10.0


def test_heuristic_merges_tiny_fragments(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "heuristic")
    monkeypatch.setattr(config, "HEURISTIC_PAUSE_GAP_SECONDS", 0.45)
    monkeypatch.setattr(config, "HEURISTIC_MIN_SEGMENT_WORDS", 6)

    words = (
        [make_word("a", i * 0.3, i * 0.3 + 0.2) for i in range(8)]
        + [make_word("short", 10.0, 10.2), make_word("bit", 10.3, 10.5)]  # 2 words < 6
        + [make_word("b", 20.0, 20.2) for _ in range(8)]
    )
    segments = concept_segmenter.segment_dd_block(words)
    assert len(segments) == 2  # fragment merged into previous, not its own segment


def test_heuristic_topic_skips_stopwords(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "heuristic")
    monkeypatch.setattr(config, "HEURISTIC_PAUSE_GAP_SECONDS", 0.45)
    monkeypatch.setattr(config, "HEURISTIC_MIN_SEGMENT_WORDS", 6)

    words = [make_word(w, i * 0.2, i * 0.2 + 0.15) for i, w in enumerate(
        ["so", "let", "me", "explain", "neuron", "summation", "now", "inputs", "weights", "bias", "sums"]
    )]
    segments = concept_segmenter.segment_dd_block(words)
    assert len(segments) == 1
    # Stopwords (so/let/me) are dropped; first 4 significant words label it
    assert segments[0].topic == "explain neuron summation inputs"


def test_heuristic_empty_words(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "heuristic")
    assert concept_segmenter.segment_dd_block([]) == []


# ---------------------------------------------------------------------------
# JSON extraction robustness
# ---------------------------------------------------------------------------

def test_extract_json_plain():
    assert concept_segmenter._extract_json('[{"a": 1}]') == '[{"a": 1}]'


def test_extract_json_markdown_fence():
    raw = '```json\n[{"a": 1}]\n```'
    assert concept_segmenter._extract_json(raw) == '[{"a": 1}]'


def test_extract_json_preamble_and_fence():
    raw = 'Sure, here is the segmentation:\n```json\n[{"a": 1}]\n```\nLet me know!'
    assert concept_segmenter._extract_json(raw) == '[{"a": 1}]'


def test_extract_json_array_inside_prose():
    raw = 'The result is [{"topic": "x", "start_word_index": 0, "end_word_index": 3}] as requested.'
    assert '[{"topic"' in concept_segmenter._extract_json(raw)


# ---------------------------------------------------------------------------
# Ollama mode (mocked)
# ---------------------------------------------------------------------------

GOOD_PAYLOAD = (
    '[{"topic": "single neuron summation", "start_word_index": 0, "end_word_index": 4},'
    ' {"topic": "neural network layers", "start_word_index": 5, "end_word_index": 9}]'
)


def _words(n=10):
    return [make_word(f"w{i}", i * 0.5, i * 0.5 + 0.3) for i in range(n)]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_ollama_mode_happy_path(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": GOOD_PAYLOAD}))

    segments = concept_segmenter.segment_dd_block(_words())
    assert len(segments) == 2
    assert segments[0].topic == "single neuron summation"
    assert segments[0].start == 0.0
    assert segments[1].start == 2.5  # word 5 start
    assert "w5 w6 w7 w8 w9" in segments[1].transcript_excerpt


def test_ollama_mode_fenced_json(monkeypatch):
    """Markdown fences around otherwise-valid JSON should just work."""
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": f"```json\n{GOOD_PAYLOAD}\n```"}))

    segments = concept_segmenter.segment_dd_block(_words())
    assert len(segments) == 2


def test_ollama_mode_retry_recovers_from_bad_json(monkeypatch):
    """First response is garbage, corrected second response is used."""
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    payloads = iter(["oops here's some chatter, no json", GOOD_PAYLOAD])

    def fake_post(*a, **k):
        return FakeResponse({"response": next(payloads)})

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    segments = concept_segmenter.segment_dd_block(_words())
    assert len(segments) == 2


def test_ollama_mode_fails_after_exhausted_retries(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": "not json at all"}))

    with pytest.raises(ValueError, match="unusable"):
        concept_segmenter.segment_dd_block(_words())


def test_ollama_mode_skips_malformed_segments(monkeypatch):
    """One malformed entry (missing keys) is skipped, not fatal."""
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    payload = (
        '[{"topic": "ok concept", "start_word_index": 0, "end_word_index": 4},'
        ' {"topic": "broken"}]'
    )
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": payload}))

    segments = concept_segmenter.segment_dd_block(_words())
    assert len(segments) == 1
    assert segments[0].topic == "ok concept"


def test_ollama_unreachable_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_FALLBACK", True)

    def refuse(*a, **k):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(ollama_client.requests, "post", refuse)

    # Words with a pause so heuristic mode yields 2 segments
    words = _words(8) + [make_word("later", 100.0, 100.2)] + _words(8)
    segments = concept_segmenter.segment_dd_block(words)
    assert len(segments) == 2  # heuristic fallback produced segments, no raise


def test_ollama_unreachable_hard_fail_when_fallback_disabled(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "ollama")
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_FALLBACK", False)

    def refuse(*a, **k):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(ollama_client.requests, "post", refuse)

    with pytest.raises(requests.ConnectionError):
        concept_segmenter.segment_dd_block(_words())


def test_invalid_mode_raises(monkeypatch):
    monkeypatch.setattr(config, "CONCEPT_SEGMENTATION_MODE", "gibberish")
    with pytest.raises(ValueError, match="CONCEPT_SEGMENTATION_MODE"):
        concept_segmenter.segment_dd_block(_words())
