"""
cut_processor.py

Takes the parsed command spans (from command_parser.py) and produces
a concrete list of "keep" segments — the inverse of everything marked
for removal. This keep-list is what actually gets handed to ffmpeg to
build the final trimmed video.

Removal includes:
  1. Every CUT span's content (the footage between "cut" and "cut")
  2. Every spoken command word itself (both "cut"s and both "dd"s),
     regardless of span type, so you never hear yourself saying the
     command in the final render.

DD span CONTENT is never removed here — it's kept and handed to
dd_processor.py for visual insertion. Only the spoken "dd" words
themselves are removed (handled by the shared command-word removal
step, same as cuts).
"""

from __future__ import annotations

from dataclasses import dataclass

from command_parser import ParseResult, get_all_command_word_removal_ranges
from config import COMMAND_WORD_PADDING_SECONDS


@dataclass
class KeepSegment:
    start: float
    end: float


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping or touching (start, end) ranges into a minimal set."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def build_keep_segments(
    result: ParseResult, total_duration_seconds: float
) -> list[KeepSegment]:
    """
    Given the full parse result and the total video duration, compute
    every segment of the video that should be KEPT in the final render.

    Logic: start with "keep everything", then subtract every CUT span's
    content and every spoken command word (from both CUT and DD spans).
    """
    removal_ranges: list[tuple[float, float]] = []

    # 1. CUT span content — the whole point of a cut is to remove it
    for cut in result.cut_spans:
        removal_ranges.append((cut.content_start, cut.content_end))

    # 2. Every spoken command word (cut AND dd), so they're never heard
    removal_ranges.extend(
        get_all_command_word_removal_ranges(result, COMMAND_WORD_PADDING_SECONDS)
    )

    merged_removals = _merge_ranges(removal_ranges)

    # Invert: build keep segments as the gaps between removals
    keep_segments: list[KeepSegment] = []
    cursor = 0.0
    for start, end in merged_removals:
        start = max(0.0, start)
        end = min(total_duration_seconds, end)
        if start > cursor:
            keep_segments.append(KeepSegment(start=cursor, end=start))
        cursor = max(cursor, end)

    if cursor < total_duration_seconds:
        keep_segments.append(KeepSegment(start=cursor, end=total_duration_seconds))

    # Drop degenerate zero-or-negative-length segments that can result
    # from padding pushing a removal range past a keep boundary.
    keep_segments = [s for s in keep_segments if s.end - s.start > 0.01]

    return keep_segments


def build_ffmpeg_filter_complex(keep_segments: list[KeepSegment]) -> str:
    """
    Builds an ffmpeg filter_complex string that trims and concatenates
    the keep segments into one continuous output stream (video + audio).

    This uses the trim + concat filter approach, which re-encodes but
    is far more reliable than stream-copy trimming for frame-accurate
    cuts at arbitrary (non-keyframe) timestamps — important here since
    cut points are determined by speech, not by keyframes.
    """
    if not keep_segments:
        raise ValueError("No keep segments — the entire video would be removed. Check your cut commands.")

    video_parts = []
    audio_parts = []
    for i, seg in enumerate(keep_segments):
        video_parts.append(
            f"[0:v]trim=start={seg.start:.3f}:end={seg.end:.3f},"
            f"setpts=PTS-STARTPTS[v{i}];"
        )
        audio_parts.append(
            f"[0:a]atrim=start={seg.start:.3f}:end={seg.end:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}];"
        )

    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keep_segments)))
    concat_filter = f"{concat_inputs}concat=n={len(keep_segments)}:v=1:a=1[outv][outa]"

    filter_complex = "".join(video_parts) + "".join(audio_parts) + concat_filter
    return filter_complex


if __name__ == "__main__":
    import argparse
    import json

    from command_parser import parse_commands

    parser = argparse.ArgumentParser(description="Build a keep-segment cut plan from a transcript.")
    parser.add_argument("transcript_json", help="Path to word-level transcript JSON")
    parser.add_argument("duration", type=float, help="Total video duration in seconds")
    args = parser.parse_args()

    with open(args.transcript_json, "r", encoding="utf-8") as f:
        words = json.load(f)

    result = parse_commands(words)
    keep_segments = build_keep_segments(result, args.duration)

    print(f"Keeping {len(keep_segments)} segment(s), total duration:")
    total = sum(s.end - s.start for s in keep_segments)
    print(f"  {total:.1f}s of {args.duration:.1f}s original ({total/args.duration*100:.1f}% kept)\n")
    for s in keep_segments:
        print(f"  keep {s.start:.2f}s -> {s.end:.2f}s ({s.end - s.start:.2f}s)")

    print("\nffmpeg filter_complex preview:")
    print(build_ffmpeg_filter_complex(keep_segments))
