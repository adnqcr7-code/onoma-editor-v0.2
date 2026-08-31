"""
Tests for svg_generator.py — SVG extraction + structural validation.

No network access: Ollama POSTs are monkeypatched where needed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import ollama_client  # noqa: E402
import svg_generator  # noqa: E402


GOOD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"><text x="10" y="30">hi</text></svg>'


# ---------------------------------------------------------------------------
# _extract_svg
# ---------------------------------------------------------------------------

def test_extract_svg_plain():
    assert svg_generator._extract_svg(GOOD_SVG) == GOOD_SVG


def test_extract_svg_markdown_fence():
    raw = f"```svg\n{GOOD_SVG}\n```"
    assert svg_generator._extract_svg(raw) == GOOD_SVG


def test_extract_svg_preamble():
    raw = f"Here's the diagram you asked for:\n{GOOD_SVG}\nHope that helps!"
    assert svg_generator._extract_svg(raw) == GOOD_SVG


# ---------------------------------------------------------------------------
# validate_svg_document
# ---------------------------------------------------------------------------

def test_validate_accepts_good_svg():
    assert svg_generator.validate_svg_document(GOOD_SVG) == GOOD_SVG


def test_validate_rejects_non_svg():
    with pytest.raises(ValueError, match="does not start with"):
        svg_generator.validate_svg_document("Here is a diagram of a neuron.")


def test_validate_rejects_truncated():
    # Self-closed root: well-formed XML, but not a complete <svg>...</svg>
    # document — the classic "generation stopped early" shape.
    truncated = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"/>'
    with pytest.raises(ValueError, match="truncated"):
        svg_generator.validate_svg_document(truncated)


def test_validate_rejects_unclosed_element():
    # Unclosed tag -> caught by the XML well-formedness check
    broken = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"><circle cx="10" cy="10" r="5"/></svg>'
    broken = broken.replace("</svg>", "")  # leave it truly unclosed
    with pytest.raises(ValueError, match="well-formed"):
        svg_generator.validate_svg_document(broken)


def test_validate_rejects_malformed_xml():
    broken = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"><circle cx="10"></svg>'
    with pytest.raises(ValueError, match="well-formed"):
        svg_generator.validate_svg_document(broken)


def test_validate_rejects_missing_viewbox():
    no_vb = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(ValueError, match="viewBox"):
        svg_generator.validate_svg_document(no_vb)


def test_validate_rejects_wrong_root():
    # Starts with "<svg" (passes the prefix check) but the root
    # element itself is not svg.
    wrong_root = '<svgwrong xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"></svgwrong>'
    with pytest.raises(ValueError, match="root element"):
        svg_generator.validate_svg_document(wrong_root)


def test_validate_rejects_non_svg_prefix():
    with pytest.raises(ValueError, match="does not start with"):
        svg_generator.validate_svg_document('<html viewBox="0 0 800 600"></html>')


# ---------------------------------------------------------------------------
# generate_svg (mocked Ollama, retry behavior)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_generate_svg_success(monkeypatch):
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": GOOD_SVG}))
    result = svg_generator.generate_svg("neural network layers", "explain layers")
    assert result == GOOD_SVG


def test_generate_svg_retries_then_succeeds(monkeypatch):
    """Chatter + fence first, clean SVG second — one corrective retry."""
    payloads = iter([
        "Sure! Here's your diagram:\n```svg\n" + GOOD_SVG + "\n```",  # fenced: extraction saves it -> actually valid
        "nope, just text, no tags",
    ])
    # Reverse: first response is truly invalid, second is fenced-but-valid.
    payloads = iter([
        "I cannot draw but here are some words",
        f"```svg\n{GOOD_SVG}\n```",
    ])

    def fake_post(*a, **k):
        return FakeResponse({"response": next(payloads)})

    monkeypatch.setattr(ollama_client.requests, "post", fake_post)
    result = svg_generator.generate_svg("topic", "excerpt")
    assert result == GOOD_SVG


def test_generate_svg_fails_after_retries(monkeypatch):
    monkeypatch.setattr(ollama_client.requests, "post",
                        lambda *a, **k: FakeResponse({"response": "still not svg"}))
    with pytest.raises(ValueError, match="failed validation"):
        svg_generator.generate_svg("topic", "excerpt")
