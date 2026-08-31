r"""
caption_generator.py

Converts word-level transcript timestamps into a styled .ass subtitle
file, ready to be burned into the final video with ffmpeg.

Uses the ASS (Advanced SubStation Alpha) format because it supports
per-style font, color, outline, position, and inline color overrides
for per-word highlighting — plain .srt cannot do any of this.

Two caption modes (config.CAPTION_MODE, or ONOMA_CAPTION_MODE env var):

  "chunk"   — one caption line per short word-chunk. Simple, clean,
              what the pipeline originally shipped with.
  "karaoke" — word-by-word highlighting (the TikTok/Shorts look): the
              full chunk is always on screen, and the word being spoken
              at that instant flips to CAPTION_HIGHLIGHT_COLOR.
              Implemented by emitting one Dialogue event per word with
              an inline color override on the active word — this works
              everywhere libass runs (ffmpeg burn-in included), unlike
              ASS karaoke tags (\k) whose sweep behavior varies
              between renderers.

Chunking is pause-aware in both modes: a silence gap longer than
CAPTION_BREAK_GAP_SECONDS between two words starts a new chunk, so
caption breaks land on natural speech boundaries instead of slicing
mid-phrase.

IMPORTANT: this module only handles KEPT content — it should be run
AFTER cut_processor.py has determined which time ranges survive, and
should receive already-adjusted timestamps (i.e. timestamps relative
to the FINAL trimmed video, not the original raw footage). See
pipeline.py for how timestamps get remapped after cuts are applied.
"""

from __future__ import annotations

from pathlib import Path

import config
from config import (
    CAPTION_FONT_NAME,
    CAPTION_FONT_SIZE,
    CAPTION_PRIMARY_COLOR,
    CAPTION_OUTLINE_COLOR,
    CAPTION_BACK_COLOR,
    CAPTION_BOLD,
    CAPTION_OUTLINE_WIDTH,
    CAPTION_SHADOW,
    CAPTION_ALIGNMENT,
    CAPTION_MARGIN_V,
    CAPTION_MAX_WORDS_PER_LINE,
)
from transcribe import WordTimestamp


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.CC (centiseconds)."""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _bgr6(ass_color: str) -> str:
    """Extract the 6-hex-digit BBGGRR part from an &HAABBGGRR config color.

    Inline color overrides don't take an alpha byte, so we strip it.
    """
    color = ass_color.replace("&H", "").replace("&", "")
    if len(color) == 8:
        color = color[2:]  # drop AA
    return color.upper()


def _build_ass_header() -> str:
    bold_flag = -1 if CAPTION_BOLD else 0
    return f"""[Script Info]
Title: Onoma Editor Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{CAPTION_FONT_NAME},{CAPTION_FONT_SIZE},{CAPTION_PRIMARY_COLOR},&H000000FF,{CAPTION_OUTLINE_COLOR},{CAPTION_BACK_COLOR},{bold_flag},0,0,0,100,100,0,0,1,{CAPTION_OUTLINE_WIDTH},{CAPTION_SHADOW},{CAPTION_ALIGNMENT},20,20,{CAPTION_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _chunk_words(
    words: list[WordTimestamp],
    max_words_per_line: int,
    break_gap_seconds: float | None = None,
) -> list[list[WordTimestamp]]:
    """
    Group consecutive words into short caption chunks.

    A new chunk starts when EITHER the word count cap is hit OR (when
    break_gap_seconds is set) the speaker pauses longer than that
    between two words. Pause-based breaking keeps captions aligned with
    natural speech boundaries — flat count-based chunking slices
    mid-phrase, which reads badly.
    """
    if not words:
        return []

    chunks: list[list[WordTimestamp]] = []
    current: list[WordTimestamp] = [words[0]]

    for prev, cur in zip(words, words[1:]):
        pause = cur["start"] - prev["end"]
        gap_break = break_gap_seconds is not None and pause >= break_gap_seconds
        if len(current) >= max_words_per_line or gap_break:
            chunks.append(current)
            current = [cur]
        else:
            current.append(cur)

    chunks.append(current)
    return chunks


def _chunk_caption_lines(chunk: list[WordTimestamp]) -> list[str]:
    """One Dialogue event per chunk — plain 'chunk' mode."""
    lines = []
    start = _format_ass_time(chunk[0]["start"])
    end = _format_ass_time(chunk[-1]["end"])
    text = " ".join(w["word"] for w in chunk).strip()
    if text:
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    return lines


def _karaoke_caption_lines(chunk: list[WordTimestamp]) -> list[str]:
    """
    One Dialogue event per WORD — 'karaoke' mode.

    Every event shows the whole chunk's text; the word being spoken
    during that event is wrapped in an inline color override. Event i
    runs from word i's start to word i+1's start (so the highlight
    flips exactly when the next word begins); the last event ends at
    the chunk's final word end. This duplication approach is fully
    supported by libass (ffmpeg's subtitle renderer) — no reliance on
    renderer-specific \\k tag behavior.
    """
    if not chunk:
        return []

    highlight = _bgr6(config.CAPTION_HIGHLIGHT_COLOR)
    base = _bgr6(CAPTION_PRIMARY_COLOR)
    override = "{\\c&H" + highlight + "&}"
    restore = "{\\c&H" + base + "&}"

    lines = []
    for i, word in enumerate(chunk):
        start = word["start"]
        if i + 1 < len(chunk):
            # Flip the highlight exactly when the next word begins.
            # max() guards positive duration against overlapping
            # (end > next start) whisper timestamps.
            end = max(chunk[i + 1]["start"], start + 0.03)
        else:
            end = max(word["end"], start + 0.03)

        parts = []
        for j, w in enumerate(chunk):
            parts.append(f"{override}{w['word']}{restore}" if j == i else w["word"])
        text = " ".join(parts).strip()
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},"
            f"Default,,0,0,0,,{text}\n"
        )
    return lines


def generate_ass_captions(
    words: list[WordTimestamp],
    output_path: str | Path,
    mode: str | None = None,
) -> Path:
    """
    Generate a .ass subtitle file from word-level timestamps.

    words should already be timestamps relative to the FINAL video
    (post-cut), not the original raw recording.

    mode: "chunk" or "karaoke" — defaults to config.CAPTION_MODE.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = (mode or config.CAPTION_MODE).lower()
    if mode not in ("chunk", "karaoke"):
        raise ValueError(
            f"Caption mode must be 'chunk' or 'karaoke', got '{mode}'. "
            "Fix config.CAPTION_MODE or the ONOMA_CAPTION_MODE env var."
        )

    line_builder = _chunk_caption_lines if mode == "chunk" else _karaoke_caption_lines

    chunks = _chunk_words(
        words,
        CAPTION_MAX_WORDS_PER_LINE,
        break_gap_seconds=config.CAPTION_BREAK_GAP_SECONDS if mode == "karaoke" else None,
    )

    lines = [_build_ass_header()]
    for chunk in chunks:
        if not chunk:
            continue
        lines.extend(line_builder(chunk))

    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


def build_ffmpeg_caption_filter(ass_path: str | Path) -> str:
    """
    Returns the ffmpeg subtitles filter string to burn in the given
    .ass file. Path is escaped for ffmpeg's filter syntax (colons and
    backslashes need escaping on Windows paths in particular — this is
    relevant since Adnan is on Windows).
    """
    ass_path_str = str(Path(ass_path).resolve())
    # ffmpeg filter syntax needs colons and backslashes escaped
    escaped = ass_path_str.replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{escaped}'"


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Generate styled ASS captions from a transcript.")
    parser.add_argument("transcript_json", help="Path to word-level transcript JSON")
    parser.add_argument("--output", default="captions.ass", help="Output .ass file path")
    parser.add_argument(
        "--mode",
        choices=["chunk", "karaoke"],
        default=None,
        help="Caption mode (default: config.CAPTION_MODE)",
    )
    args = parser.parse_args()

    with open(args.transcript_json, "r", encoding="utf-8") as f:
        words = json.load(f)

    out = generate_ass_captions(words, args.output, mode=args.mode)
    print(f"Generated captions -> {out} (mode: {args.mode or config.CAPTION_MODE})")
    print(f"ffmpeg filter: {build_ffmpeg_caption_filter(out)}")
