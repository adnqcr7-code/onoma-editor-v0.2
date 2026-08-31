"""
transcribe.py

Thin wrapper around faster-whisper for local, free, word-level
transcription. This is the foundation everything else builds on — cut
detection, dd-block detection, and captions all depend on accurate
word-level timestamps.

Output format (a plain Python list of dicts, also JSON-serializable):

[
    {
        "word": "cut",
        "start": 12.34,
        "end": 12.61,
        "confidence": 0.98
    },
    ...
]

This flat word-level format is deliberately simple so every downstream
module (command_parser, caption_generator, concept_segmenter) can work
with the same shape without re-parsing anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
)


class WordTimestamp(TypedDict):
    word: str
    start: float
    end: float
    confidence: float


def transcribe_audio(audio_path: str | Path) -> list[WordTimestamp]:
    """
    Transcribe an audio/video file and return word-level timestamps.

    Requires faster-whisper to be installed and, ideally, an NVIDIA GPU
    for reasonable speed on an hour of footage. On CPU-only machines,
    set WHISPER_DEVICE = "cpu" and WHISPER_COMPUTE_TYPE = "int8" in
    config.py — it will be much slower (potentially 30-60+ minutes for
    an hour of audio) but will still work.

    Raises:
        ImportError: if faster-whisper is not installed.
        FileNotFoundError: if audio_path does not exist.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio/video file not found: {audio_path}")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError(
            "faster-whisper is not installed. Run:\n"
            "  pip install faster-whisper --break-system-packages\n"
            "See requirements.txt for the full dependency list."
        ) from exc

    model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )

    segments, _info = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        word_timestamps=True,
        vad_filter=True,  # skip silence, improves accuracy and speed
    )

    words: list[WordTimestamp] = []
    for segment in segments:
        if segment.words is None:
            continue
        for w in segment.words:
            words.append(
                {
                    "word": w.word.strip().lower(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "confidence": round(getattr(w, "probability", 1.0), 3),
                }
            )

    return words


def transcribe_and_save(audio_path: str | Path, output_json_path: str | Path) -> list[WordTimestamp]:
    """
    Convenience wrapper: transcribe and immediately save to a JSON file
    so later pipeline stages (or a re-run) don't need to re-transcribe,
    which is by far the slowest step for long footage.
    """
    words = transcribe_audio(audio_path)
    output_json_path = Path(output_json_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
    return words


def load_transcript(json_path: str | Path) -> list[WordTimestamp]:
    """Load a previously saved word-level transcript from JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe a video/audio file with word-level timestamps.")
    parser.add_argument("input", help="Path to video or audio file")
    parser.add_argument("--output", default=None, help="Path to save JSON transcript (default: input path with .json extension)")
    args = parser.parse_args()

    out_path = args.output or str(Path(args.input).with_suffix(".transcript.json"))
    result = transcribe_and_save(args.input, out_path)
    print(f"Transcribed {len(result)} words -> {out_path}")
