"""
command_parser.py

Parses spoken voice commands out of a word-level transcript.

This is the foundation of the whole "no manual timeline" workflow:
you say "cut" ... "cut" to mark a removal span, and "dd" ... "dd" to
mark an explanation block. This module finds those pairs reliably,
including handling messy real-world cases:

- An odd number of command words (you said "cut" but forgot the second one)
- Two different command types overlapping (a "dd" block containing a "cut")
- The same command word appearing very far apart in time (unrelated to
  each other, not a real pair)
- Command words that are also normal words in your speech (e.g. if you
  ever genuinely need to say "cut" as English, not as a command) — this
  is a known limitation, documented below, not silently ignored.

This module is fully deterministic and fully testable — no LLM calls
here. That's intentional: cut/dd boundary detection should never be
fuzzy or probabilistic, it's a hard on/off signal from you.

KNOWN LIMITATION (flagging honestly, not hiding it):
Because "cut" and "dd" are matched as literal spoken words, if you ever
say them as normal English in your explanation (e.g. "let's cut to the
chase" or a word that sounds like "dd"), this parser has no way to
distinguish that from an actual command. Mitigations documented in
docs/COMMAND_VOCABULARY.md — either avoid using CUT_COMMAND_WORD /
DD_COMMAND_WORD in normal narration, or switch to a more distinctive
command word in config.py (e.g. "cutnow" said as one word, or a rare
word like "onomacut"). This tradeoff is Adnan's call, not something to
silently paper over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from config import (
    CUT_COMMAND_WORD,
    DD_COMMAND_WORD,
    MAX_COMMAND_PAIR_GAP_SECONDS,
)
from transcribe import WordTimestamp


class CommandType(str, Enum):
    CUT = "cut"
    DD = "dd"


@dataclass
class CommandSpan:
    """A matched start/end pair of a spoken command."""

    command_type: CommandType
    start_word_time: float  # timestamp of the FIRST spoken command word (start marker)
    start_word_end_time: float  # end of that spoken word (for audio removal padding)
    end_word_time: float  # timestamp of the SECOND spoken command word (end marker)
    end_word_end_time: float
    content_start: float = field(init=False)  # start of the actual content between commands
    content_end: float = field(init=False)  # end of the actual content between commands

    def __post_init__(self) -> None:
        # The "content" is everything strictly between the two spoken
        # command words — the command words themselves are not content
        # and get removed along with everything they bracket, for CUT.
        # For DD, the command words are also removed but the content
        # between them is KEPT and processed for visuals, not deleted.
        self.content_start = self.start_word_end_time
        self.content_end = self.end_word_time


@dataclass
class ParseWarning:
    """A non-fatal issue found during parsing, surfaced to the user/agent
    rather than silently dropped or silently guessed at."""

    message: str
    word_time: float | None = None


@dataclass
class ParseResult:
    cut_spans: list[CommandSpan]
    dd_spans: list[CommandSpan]
    warnings: list[ParseWarning]


def _find_command_occurrences(
    words: list[WordTimestamp], command_word: str
) -> list[WordTimestamp]:
    """Find every occurrence of a command word in the transcript, in order."""
    target = command_word.strip().lower()
    return [w for w in words if w["word"].strip(".,!?").lower() == target]


def _pair_occurrences(
    occurrences: list[WordTimestamp],
    command_type: CommandType,
    max_gap_seconds: float,
    warnings: list[ParseWarning],
) -> list[CommandSpan]:
    """
    Pair up consecutive occurrences of a command word into start/end
    spans: 1st = start, 2nd = end, 3rd = start, 4th = end, etc.

    This is a simple alternating pairing, which matches the described
    workflow exactly ("first cut marks start, second cut marks end").
    If there's an odd number left over at the end, that final one is
    an unmatched start — surfaced as a warning, never silently dropped,
    because silently dropping it could mean losing footage the user
    intended to keep, or keeping footage they intended to cut.
    """
    spans: list[CommandSpan] = []
    i = 0
    while i + 1 < len(occurrences):
        start_word = occurrences[i]
        end_word = occurrences[i + 1]

        gap = end_word["start"] - start_word["start"]
        if gap > max_gap_seconds:
            warnings.append(
                ParseWarning(
                    message=(
                        f"{command_type.value} command at {start_word['start']:.1f}s "
                        f"and the next {command_type.value} at {end_word['start']:.1f}s "
                        f"are {gap:.0f}s apart, further than "
                        f"MAX_COMMAND_PAIR_GAP_SECONDS ({max_gap_seconds}s). "
                        "Pairing them anyway, but this may be two unrelated "
                        "commands rather than a real start/end pair. Review "
                        "this span manually before trusting the auto-render."
                    ),
                    word_time=start_word["start"],
                )
            )

        spans.append(
            CommandSpan(
                command_type=command_type,
                start_word_time=start_word["start"],
                start_word_end_time=start_word["end"],
                end_word_time=end_word["start"],
                end_word_end_time=end_word["end"],
            )
        )
        i += 2

    # Odd one out: an unmatched start with no end
    if i < len(occurrences):
        leftover = occurrences[i]
        warnings.append(
            ParseWarning(
                message=(
                    f"Unmatched {command_type.value} command at "
                    f"{leftover['start']:.1f}s — no closing "
                    f"'{command_type.value}' found after it. This span will "
                    "NOT be processed. Did you forget to say the closing "
                    "command, or was this an accidental extra word?"
                ),
                word_time=leftover["start"],
            )
        )

    return spans


def _check_overlaps(
    cut_spans: list[CommandSpan],
    dd_spans: list[CommandSpan],
    warnings: list[ParseWarning],
) -> None:
    """
    Flag (don't silently resolve) any case where a cut span and a dd
    span overlap in time. This is genuinely ambiguous — did the user
    mean to cut part of an explanation block, or misspeak a command? —
    so it's surfaced for human/agent review rather than guessed at.
    """
    for cut in cut_spans:
        for dd in dd_spans:
            overlap_start = max(cut.content_start, dd.content_start)
            overlap_end = min(cut.content_end, dd.content_end)
            if overlap_start < overlap_end:
                warnings.append(
                    ParseWarning(
                        message=(
                            f"CUT span ({cut.content_start:.1f}s-{cut.content_end:.1f}s) "
                            f"overlaps with DD span "
                            f"({dd.content_start:.1f}s-{dd.content_end:.1f}s). "
                            "Resolve this manually — the pipeline will apply "
                            "the cut first, then process whatever DD content "
                            "remains, but double check this is what you meant."
                        ),
                        word_time=overlap_start,
                    )
                )


def parse_commands(words: list[WordTimestamp]) -> ParseResult:
    """
    Main entry point. Takes a full word-level transcript and returns
    every matched cut span and dd span, plus any warnings about
    ambiguous or malformed command usage.
    """
    warnings: list[ParseWarning] = []

    cut_occurrences = _find_command_occurrences(words, CUT_COMMAND_WORD)
    dd_occurrences = _find_command_occurrences(words, DD_COMMAND_WORD)

    cut_spans = _pair_occurrences(
        cut_occurrences, CommandType.CUT, MAX_COMMAND_PAIR_GAP_SECONDS, warnings
    )
    dd_spans = _pair_occurrences(
        dd_occurrences, CommandType.DD, MAX_COMMAND_PAIR_GAP_SECONDS, warnings
    )

    _check_overlaps(cut_spans, dd_spans, warnings)

    return ParseResult(cut_spans=cut_spans, dd_spans=dd_spans, warnings=warnings)


def get_all_command_word_removal_ranges(
    result: ParseResult, padding_seconds: float
) -> list[tuple[float, float]]:
    """
    Returns every (start, end) time range that corresponds to a SPOKEN
    COMMAND WORD ITSELF (not the content between commands) — these
    ranges get removed from the final audio/video regardless of
    whether the span is a CUT or a DD, because you never want to hear
    yourself saying "cut" or "dd" in the final render.
    """
    ranges: list[tuple[float, float]] = []
    all_spans = result.cut_spans + result.dd_spans
    for span in all_spans:
        ranges.append(
            (span.start_word_time - padding_seconds, span.start_word_end_time + padding_seconds)
        )
        ranges.append(
            (span.end_word_time - padding_seconds, span.end_word_end_time + padding_seconds)
        )
    return sorted(ranges, key=lambda r: r[0])


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Parse voice commands from a transcript JSON file.")
    parser.add_argument("transcript_json", help="Path to word-level transcript JSON (from transcribe.py)")
    args = parser.parse_args()

    with open(args.transcript_json, "r", encoding="utf-8") as f:
        words = json.load(f)

    result = parse_commands(words)

    print(f"Found {len(result.cut_spans)} CUT span(s):")
    for s in result.cut_spans:
        print(f"  remove {s.start_word_time:.2f}s -> {s.end_word_time:.2f}s")

    print(f"\nFound {len(result.dd_spans)} DD span(s):")
    for s in result.dd_spans:
        print(f"  explain {s.content_start:.2f}s -> {s.content_end:.2f}s")

    if result.warnings:
        print(f"\n{len(result.warnings)} WARNING(S):")
        for w in result.warnings:
            print(f"  ! {w.message}")
