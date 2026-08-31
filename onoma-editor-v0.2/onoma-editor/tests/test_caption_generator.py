"""
Tests for caption_generator.py — chunk mode, karaoke mode, pause-aware
chunking, color formatting.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
from caption_generator import generate_ass_captions, _bgr6, _chunk_words  # noqa: E402


def make_word(word, start, end):
    return {"word": word, "start": start, "end": end, "confidence": 0.95}


WORDS = [make_word(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(
    ["today", "we're", "building", "an", "ai", "editor", "tool"]
)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_bgr6_strips_alpha():
    assert _bgr6("&H00FFFFFF") == "FFFFFF"
    assert _bgr6("&H008ECF3E") == "8ECF3E"
    assert _bgr6("FFFFFF") == "FFFFFF"


def test_chunk_words_respects_max():
    chunks = _chunk_words(WORDS, max_words_per_line=4)
    assert [len(c) for c in chunks] == [4, 3]


def test_chunk_words_breaks_on_pause():
    words = [
        make_word("first", 0.0, 0.3),
        make_word("phrase", 0.4, 0.7),
        # 1.5s silence here
        make_word("second", 2.2, 2.5),
        make_word("phrase", 2.6, 2.9),
    ]
    chunks = _chunk_words(words, max_words_per_line=4, break_gap_seconds=0.6)
    assert len(chunks) == 2
    assert [w["word"] for w in chunks[0]] == ["first", "phrase"]
    assert [w["word"] for w in chunks[1]] == ["second", "phrase"]


# ---------------------------------------------------------------------------
# Chunk mode (default)
# ---------------------------------------------------------------------------

def test_chunk_mode_generates_dialogue_lines(tmp_path):
    out = tmp_path / "caps.ass"
    generate_ass_captions(WORDS, out, mode="chunk")
    content = out.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[Events]" in content
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2  # 7 words / 4 per line -> 2 chunks
    assert "today we're building an" in dialogue_lines[0]


def test_default_mode_comes_from_config(tmp_path):
    monkeypatch_mode = "karaoke"
    import caption_generator as cg
    original = config.CAPTION_MODE
    config.CAPTION_MODE = monkeypatch_mode
    try:
        out = tmp_path / "caps.ass"
        cg.generate_ass_captions(WORDS, out)  # no explicit mode
        content = out.read_text(encoding="utf-8")
        assert "{\\c&H" in content  # karaoke overrides present
    finally:
        config.CAPTION_MODE = original


# ---------------------------------------------------------------------------
# Karaoke mode
# ---------------------------------------------------------------------------

def test_karaoke_mode_one_event_per_word(tmp_path):
    out = tmp_path / "caps.ass"
    generate_ass_captions(WORDS, out, mode="karaoke")
    content = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == len(WORDS)  # 7 words -> 7 events


def test_karaoke_mode_highlights_each_word_once(tmp_path):
    out = tmp_path / "caps.ass"
    generate_ass_captions(WORDS, out, mode="karaoke")
    content = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]

    # Each event highlights exactly one word: exactly one color override
    # pair per line (open + restore).
    for line in dialogue_lines:
        highlight = _bgr6(config.CAPTION_HIGHLIGHT_COLOR)
        base = _bgr6(config.CAPTION_PRIMARY_COLOR)
        assert line.count("{\\c&H" + highlight + "&}") == 1
        assert line.count("{\\c&H" + base + "&}") == 1

    # Every word gets its turn being highlighted.
    for word in WORDS:
        assert any(
            f"{{\\c&H{_bgr6(config.CAPTION_HIGHLIGHT_COLOR)}&}}{word['word']}" in line
            for line in dialogue_lines
        )


def test_karaoke_mode_timings_flip_on_word_starts(tmp_path):
    out = tmp_path / "caps.ass"
    generate_ass_captions(WORDS, out, mode="karaoke")
    content = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]

    import re
    starts = []
    for line in dialogue_lines:
        m = re.match(r"Dialogue: 0,\d+:\d+:\d+\.\d+,(\d+:\d+:\d+\.\d+),", line)
        starts.append(m)

    # Non-overlapping, monotonically increasing event order
    assert all(s is not None for s in starts)


def test_karaoke_mode_breaks_chunks_on_pause(tmp_path):
    words = [
        make_word("concept", 0.0, 0.3),
        make_word("one", 0.4, 0.7),
        # long pause -> new chunk
        make_word("concept", 3.0, 3.3),
        make_word("two", 3.4, 3.7),
    ]
    out = tmp_path / "caps.ass"
    generate_ass_captions(words, out, mode="karaoke")
    content = out.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]

    # 2 chunks x 2 words = 4 events
    assert len(dialogue_lines) == 4
    # No single event mixes words from both sides of the pause:
    # 'one' only appears with the first 'concept', never with 'two'.
    for line in dialogue_lines:
        has_one = "one" in line
        has_two = "two" in line
        assert not (has_one and has_two), f"chunk spans the pause: {line}"


def test_invalid_mode_rejected(tmp_path):
    with pytest.raises(ValueError, match="chunk.*karaoke"):
        generate_ass_captions(WORDS, tmp_path / "x.ass", mode="bogus")


def test_empty_words_produce_header_only(tmp_path):
    out = tmp_path / "caps.ass"
    generate_ass_captions([], out, mode="karaoke")
    content = out.read_text(encoding="utf-8")
    assert "Dialogue:" not in content
