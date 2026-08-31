"""
pipeline.py

End-to-end orchestrator: raw footage in, final edited video out.

    python pipeline.py --input raw_footage.mp4 --output final_video.mp4

This wires together every stage described in README.md. The fully
working stages (transcription, command parsing, cut processing,
captions) will run correctly today. The dd-block visual stages will
run but their OUTPUT QUALITY depends on concept_segmenter.py,
asset_matcher.py, and svg_generator.py being tuned against real
footage first — see AGENT_PROMPT.md for that finishing work.

The pipeline is written to fail loudly and specifically rather than
silently producing a broken video — each stage prints what it's doing
and raises clear errors if something upstream is missing (no Ollama
running, no ffmpeg on PATH, etc.) rather than failing deep inside
ffmpeg with a cryptic error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import sys
from pathlib import Path

import config
from caption_generator import generate_ass_captions, build_ffmpeg_caption_filter
from command_parser import parse_commands
from cut_processor import build_keep_segments, build_ffmpeg_filter_complex
from dd_processor import process_all_dd_blocks
from overlay_renderer import prepare_overlays, build_overlay_chain
from transcribe import transcribe_and_save, load_transcript
from config import (
    TMP_DIR,
    OUTPUT_VIDEO_CODEC,
    OUTPUT_X264_PRESET,
    OUTPUT_AUDIO_CODEC,
    OUTPUT_CRF,
    OUTPUT_FPS,
)


def _check_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise EnvironmentError(
            "ffmpeg not found on PATH. Install it and make sure it's "
            "accessible from the command line before running this pipeline."
        )


def _get_video_duration(video_path: Path) -> float:
    """Use ffprobe to get the exact duration of the input video."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Width/height of the input video's first video stream (via ffprobe).

    Overlay sizing is relative to the ACTUAL input resolution — the
    pipeline renders at input resolution (it does not rescale), so
    config.OUTPUT_RESOLUTION is not used here.
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width_str, height_str = result.stdout.strip().split("x")
    return int(width_str), int(height_str)


def _remap_timestamps_after_cuts(
    words: list[dict], keep_segments: list
) -> list[dict]:
    """
    After cuts are applied, timestamps in the ORIGINAL transcript no
    longer match positions in the FINAL trimmed video. This remaps
    each kept word's timestamp to its new position in the output
    timeline, so captions (and dd-block visual placements) line up
    correctly with the actual rendered video.

    Words that fall inside a removed span are dropped entirely.
    """
    remapped = []
    cumulative_offset = 0.0

    for seg in keep_segments:
        seg_duration = seg.end - seg.start
        for w in words:
            if seg.start <= w["start"] < seg.end:
                shift = cumulative_offset - seg.start
                remapped.append(
                    {
                        **w,
                        "start": w["start"] + shift,
                        "end": min(w["end"] + shift, cumulative_offset + seg_duration),
                    }
                )
        cumulative_offset += seg_duration

    return remapped


def run_pipeline(input_path: str, output_path: str, skip_transcription_if_cached: bool = True) -> None:
    _check_ffmpeg_available()

    input_path = Path(input_path)
    output_path = Path(output_path)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    # ---- Stage 1: Transcription ----
    transcript_json_path = TMP_DIR / f"{input_path.stem}.transcript.json"
    if skip_transcription_if_cached and transcript_json_path.exists():
        print(f"[1/6] Using cached transcript: {transcript_json_path}")
        words = load_transcript(transcript_json_path)
    else:
        print("[1/6] Transcribing audio (this is the slowest step, be patient)...")
        words = transcribe_and_save(input_path, transcript_json_path)
        print(f"       Transcribed {len(words)} words.")

    # ---- Stage 2: Command parsing ----
    print("[2/6] Parsing voice commands...")
    parse_result = parse_commands(words)
    print(f"       Found {len(parse_result.cut_spans)} cut span(s), {len(parse_result.dd_spans)} dd span(s).")
    for warning in parse_result.warnings:
        print(f"       ! WARNING: {warning.message}")

    # ---- Stage 3: Cut processing ----
    print("[3/6] Building cut plan...")
    duration = _get_video_duration(input_path)
    keep_segments = build_keep_segments(parse_result, duration)
    kept_duration = sum(s.end - s.start for s in keep_segments)
    print(f"       Keeping {kept_duration:.1f}s of {duration:.1f}s original ({kept_duration/duration*100:.1f}%).")

    # ---- Stage 4: DD-block visual processing ----
    print("[4/6] Processing explanation blocks (concept segmentation + visuals)...")
    try:
        visual_placements = process_all_dd_blocks(parse_result.dd_spans, words)
        print(f"       Generated {len(visual_placements)} visual placement(s).")
    except Exception as exc:
        print(f"       ! DD-block processing failed: {exc}")
        print("       Continuing without dd-block visuals — this stage needs tuning, see AGENT_PROMPT.md")
        visual_placements = []

    # ---- Stage 5: Captions ----
    print("[5/6] Generating captions...")
    remapped_words = _remap_timestamps_after_cuts(words, keep_segments)
    ass_path = TMP_DIR / f"{input_path.stem}.captions.ass"
    generate_ass_captions(remapped_words, ass_path, mode=config.CAPTION_MODE)
    print(f"       Captions saved to {ass_path} (mode: {config.CAPTION_MODE})")

    # ---- Stage 6: Render ----
    print("[6/6] Rendering final video...")
    filter_complex = build_ffmpeg_filter_complex(keep_segments)
    caption_filter = build_ffmpeg_caption_filter(ass_path)

    # Base chain: cut/concat -> captions burned in.
    # [outv] = cut video, [outa] = cut audio. After captions: [capv].
    # NOTE 1: semicolons separate filtergraph CHAINS — the original
    #   scaffold joined filter_complex and the caption chain without
    #   one, which ffmpeg rejects ("trailing garbage"); caught by e2e.
    # NOTE 2: the caption output label must NOT collide with the trim
    #   labels (v0..vN, a0..aN) that build_ffmpeg_filter_complex uses.
    filter_parts = [f"{filter_complex};[outv]{caption_filter}[capv]"]

    # dd-block visuals: render SVGs to PNGs, remap their timestamps
    # through the same keep-segment math as captions, and splice timed
    # overlay filters into the chain. This is the stage that used to
    # be a NOTE: marker — visuals are now actually composited.
    extra_input_args: list[str] = []
    final_vlabel = "capv"  # label of the video stream after the last chain step
    if visual_placements:
        try:
            video_w, video_h = _get_video_dimensions(input_path)
            kept_duration = sum(s.end - s.start for s in keep_segments)
            timed_overlays = prepare_overlays(visual_placements, keep_segments, TMP_DIR)
            chain = build_overlay_chain(
                timed_overlays,
                video_width=video_w,
                video_height=video_h,
                output_duration=kept_duration,
                base_label=final_vlabel,
            )
            filter_parts.extend(chain.filter_parts)
            extra_input_args = chain.input_args
            final_vlabel = chain.final_label
            print(
                f"       Compositing {chain.count} visual overlay(s) "
                f"(position: {config.OVERLAY_POSITION}, "
                f"width: {config.OVERLAY_WIDTH_FRACTION:.0%} of frame)."
            )
            for overlay in timed_overlays:
                windows = ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in overlay.windows)
                print(f"         - {overlay.topic}: visible {windows}")
        except Exception as exc:
            # One broken overlay shouldn't lose the whole render —
            # fail soft here, loudly, and still deliver cut+captions.
            print(f"       ! WARNING: overlay compositing failed: {exc}")
            print("         Rendering WITHOUT dd-block visuals.")
            extra_input_args = []

    # Ensure a libx264-friendly pixel format regardless of overlay path.
    filter_parts.append(f"[{final_vlabel}]format=yuv420p[vout]")

    full_filter = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        *extra_input_args,
        "-filter_complex", full_filter,
        "-map", "[vout]",
        "-map", "[outa]",
        "-c:v", OUTPUT_VIDEO_CODEC,
        "-preset", OUTPUT_X264_PRESET,
        "-crf", str(OUTPUT_CRF),
        "-r", str(OUTPUT_FPS),
        "-c:a", OUTPUT_AUDIO_CODEC,
        str(output_path),
    ]

    print(f"       Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("       ffmpeg STDERR:")
        print(result.stderr[-3000:])  # last part of stderr, usually where the real error is
        raise RuntimeError("ffmpeg render failed — see stderr output above.")

    print(f"\nDone. Output: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full Onoma Editor pipeline.")
    parser.add_argument("--input", required=True, help="Path to raw input video")
    parser.add_argument("--output", required=True, help="Path for final output video")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force re-transcription even if a cached transcript exists",
    )
    args = parser.parse_args()

    try:
        run_pipeline(args.input, args.output, skip_transcription_if_cached=not args.no_cache)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
