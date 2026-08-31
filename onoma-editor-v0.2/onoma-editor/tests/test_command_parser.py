"""
Tests for command_parser.py — the most critical module in this system,
since every downstream stage depends on correct cut/dd span detection.

Run with:
    cd src && python -m pytest ../tests/test_command_parser.py -v

(run from src/ so the local imports in command_parser.py resolve
correctly — see AGENT_PROMPT.md note about import structure)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from command_parser import parse_commands, CommandType  # noqa: E402


def make_word(word: str, start: float, end: float) -> dict:
    return {"word": word, "start": start, "end": end, "confidence": 0.95}


def test_simple_cut_pair():
    words = [
        make_word("hello", 0.0, 0.5),
        make_word("cut", 1.0, 1.2),
        make_word("this", 1.2, 1.5),
        make_word("part", 1.5, 1.8),
        make_word("cut", 2.0, 2.2),
        make_word("world", 2.2, 2.5),
    ]
    result = parse_commands(words)
    assert len(result.cut_spans) == 1
    assert result.cut_spans[0].command_type == CommandType.CUT
    assert result.cut_spans[0].content_start == 1.2  # end of first "cut"
    assert result.cut_spans[0].content_end == 2.0    # start of second "cut"
    assert len(result.warnings) == 0


def test_simple_dd_pair():
    words = [
        make_word("dd", 0.0, 0.2),
        make_word("explaining", 0.2, 0.6),
        make_word("stuff", 0.6, 0.9),
        make_word("dd", 1.0, 1.2),
    ]
    result = parse_commands(words)
    assert len(result.dd_spans) == 1
    assert result.dd_spans[0].content_start == 0.2
    assert result.dd_spans[0].content_end == 1.0


def test_multiple_cut_pairs():
    words = [
        make_word("cut", 1.0, 1.2),
        make_word("bad", 1.2, 1.4),
        make_word("cut", 1.5, 1.7),
        make_word("good", 2.0, 2.3),
        make_word("cut", 3.0, 3.2),
        make_word("bad2", 3.2, 3.4),
        make_word("cut", 3.5, 3.7),
    ]
    result = parse_commands(words)
    assert len(result.cut_spans) == 2
    assert result.cut_spans[0].content_start == 1.2
    assert result.cut_spans[0].content_end == 1.5
    assert result.cut_spans[1].content_start == 3.2
    assert result.cut_spans[1].content_end == 3.5


def test_unmatched_command_produces_warning_not_crash():
    words = [
        make_word("cut", 1.0, 1.2),
        make_word("oops", 1.2, 1.5),
        # no second "cut" — forgot to close it
    ]
    result = parse_commands(words)
    assert len(result.cut_spans) == 0
    assert len(result.warnings) == 1
    assert "unmatched" in result.warnings[0].message.lower()


def test_no_commands_at_all():
    words = [
        make_word("just", 0.0, 0.3),
        make_word("talking", 0.3, 0.7),
        make_word("normally", 0.7, 1.2),
    ]
    result = parse_commands(words)
    assert len(result.cut_spans) == 0
    assert len(result.dd_spans) == 0
    assert len(result.warnings) == 0


def test_cut_and_dd_do_not_interfere():
    words = [
        make_word("dd", 0.0, 0.2),
        make_word("explaining", 0.2, 0.6),
        make_word("dd", 1.0, 1.2),
        make_word("cut", 2.0, 2.2),
        make_word("mistake", 2.2, 2.5),
        make_word("cut", 3.0, 3.2),
    ]
    result = parse_commands(words)
    assert len(result.dd_spans) == 1
    assert len(result.cut_spans) == 1
    # no overlap in this case, so no warnings
    assert len(result.warnings) == 0


def test_overlapping_cut_and_dd_produces_warning():
    words = [
        make_word("dd", 0.0, 0.2),
        make_word("explaining", 0.2, 0.6),
        make_word("cut", 0.8, 1.0),
        make_word("bad", 1.0, 1.3),
        make_word("cut", 1.5, 1.7),
        make_word("more", 1.7, 2.0),
        make_word("dd", 2.5, 2.7),
    ]
    result = parse_commands(words)
    assert len(result.dd_spans) == 1
    assert len(result.cut_spans) == 1
    assert len(result.warnings) == 1
    assert "overlap" in result.warnings[0].message.lower()


def test_case_and_punctuation_insensitive_matching():
    words = [
        make_word("Cut", 1.0, 1.2),
        make_word("stuff", 1.2, 1.5),
        make_word("cut.", 2.0, 2.2),  # trailing punctuation, common in real Whisper output
    ]
    result = parse_commands(words)
    assert len(result.cut_spans) == 1


def test_sample_transcript_fixture():
    """Integration-style test against the realistic sample fixture."""
    import json

    fixture_path = Path(__file__).resolve().parent / "sample_transcript.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        words = json.load(f)

    result = parse_commands(words)
    # sample_transcript.json has exactly 1 cut pair and 1 dd pair
    assert len(result.cut_spans) == 1
    assert len(result.dd_spans) == 1
    assert len(result.warnings) == 0
