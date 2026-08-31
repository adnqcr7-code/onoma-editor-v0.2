"""
concept_segmenter.py

STATUS: Real, callable implementation with a carefully written prompt —
but NOT yet tuned against real footage. This is the piece the
AGENT_PROMPT.md hands off for iteration, because getting concept
boundaries right requires testing against Adnan's actual speaking
style and adjusting the prompt based on real failures, which can't be
done blind.

Takes the transcript text INSIDE one DD block (between the two spoken
"dd" commands) and asks a local LLM (via Ollama, e.g. Gemma) to break
it into concept segments — each with a short topic label and the
timestamp range it covers. This is what lets the pipeline know "he's
now talking about layers" vs "he's now talking about inputs" without
Adnan tagging every sub-part by hand.

Design choices worth knowing about:

- This runs as a POST-PROCESSING pass (per your decision), not live.
  It receives the full dd-block transcript at once, not a stream.
- One Ollama call per dd-block, not per word/sentence — keeps this
  fast and avoids the LLM losing context between calls.
- The prompt asks for STRICT JSON output to keep parsing reliable.
  Local models can still occasionally wrap output in markdown code
  fences or add commentary — _extract_json handles common cases, and
  anything it can't handle goes through ollama_client's
  retry-with-correction loop (the model is told exactly what was wrong
  and asked again) before this raises.
- DETERMINISTIC FALLBACK: if Ollama is unreachable (or
  ONOMA_SEGMENTATION_MODE=heuristic), a pause-gap heuristic segments
  the block without any LLM. Topic labels are cruder, so asset
  matching will miss more — but you get cut+caption+whatever visuals
  DO match instead of losing the whole stage. Logged loudly, never
  silent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

import config
from ollama_client import generate_validated
from transcribe import WordTimestamp


@dataclass
class ConceptSegment:
    topic: str  # short label, e.g. "input layer", "activation function"
    start: float
    end: float
    transcript_excerpt: str  # the actual words spoken during this segment


SEGMENTATION_PROMPT_TEMPLATE = """You are analyzing a transcript segment from a coding/AI tutorial video. The speaker is explaining a technical concept out loud while screen-recording.

Your job: break this transcript into distinct CONCEPT SEGMENTS — each segment covers one sub-topic or one step of the explanation. A new segment should start whenever the speaker moves on to explain a genuinely different part of the concept (e.g. moving from "what an input is" to "what a layer is" to "what the output is").

Do NOT create a new segment for:
- Filler words, false starts, or self-corrections
- Restating or rephrasing the same point
- Brief asides that return to the same topic

Each segment needs:
- "topic": a short (2-5 word) label for what's being explained in this segment. This label will be used to search for a matching visual asset, so make it a concrete noun phrase (e.g. "neural network layers", "single neuron summation"), not a vague description (e.g. NOT "explaining stuff").
- "start_word_index": the index (0-based) of the FIRST word in this segment, from the WORD LIST below.
- "end_word_index": the index (0-based) of the LAST word in this segment, from the WORD LIST below.

Respond with ONLY a JSON array, no other text, no markdown code fences. Example format:
[
  {{"topic": "single neuron summation", "start_word_index": 0, "end_word_index": 14}},
  {{"topic": "neural network layers", "start_word_index": 15, "end_word_index": 42}}
]

WORD LIST (index: word):
{word_list}

Respond with ONLY the JSON array."""


def _build_word_list_str(words: list[WordTimestamp]) -> str:
    return "\n".join(f"{i}: {w['word']}" for i, w in enumerate(words))


def _extract_json(raw_response: str) -> str:
    """
    Local LLMs frequently wrap JSON in markdown fences or add a short
    preamble despite instructions not to. This strips common wrappers.
    Anything this can't recover goes to the retry-with-correction loop
    in ollama_client.generate_validated before we give up.
    """
    text = raw_response.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    array_match = re.search(r"(\[.*\])", text, re.DOTALL)
    if array_match:
        return array_match.group(1)
    return text


# Words ignored when building heuristic topic labels — they say nothing
# about WHAT is being explained. Kept deliberately small: over-filtering
# makes labels like "sums inputs" become just "sums".
_HEURISTIC_STOPWORDS = {
    "so", "and", "now", "let's", "lets", "let", "me", "look", "at", "the",
    "a", "an", "this", "that", "is", "are", "it", "its", "we", "we're",
    "to", "of", "in", "for", "on", "you", "i", "um", "uh", "ok", "okay",
    "right", "basically", "like", "here", "there", "then", "next", "into",
}


def _heuristic_topic(words: list[WordTimestamp]) -> str:
    """Build a crude topic label from a segment's own words."""
    significant = [w["word"] for w in words if w["word"].lower() not in _HEURISTIC_STOPWORDS]
    label = " ".join(significant[:4])
    return label or "unnamed concept"


def _heuristic_segment(
    words: list[WordTimestamp],
    pause_gap_seconds: float,
    min_segment_words: int,
) -> list[ConceptSegment]:
    """
    Deterministic, no-LLM segmentation: a pause of silence longer than
    pause_gap_seconds between two words starts a new concept segment.
    Fragments shorter than min_segment_words merge into the previous
    segment (a mid-sentence breath shouldn't split a concept in two).

    This produces WEAKER topic labels than the LLM ("sums inputs single"
    vs "single neuron summation"), so expect more asset-match misses.
    It exists so the pipeline degrades to "some visuals" instead of
    "no visuals" when Ollama is down — and so tests can run offline.
    """
    if not words:
        return []

    groups: list[list[WordTimestamp]] = [[words[0]]]
    for prev, cur in zip(words, words[1:]):
        if cur["start"] - prev["end"] >= pause_gap_seconds:
            groups.append([cur])
        else:
            groups[-1].append(cur)

    # Merge tiny fragments into their predecessor
    merged: list[list[WordTimestamp]] = [groups[0]]
    for group in groups[1:]:
        if len(group) < min_segment_words:
            merged[-1].extend(group)
        else:
            merged.append(group)

    segments: list[ConceptSegment] = []
    for group in merged:
        if not group:
            continue
        segments.append(
            ConceptSegment(
                topic=_heuristic_topic(group),
                start=group[0]["start"],
                end=group[-1]["end"],
                transcript_excerpt=" ".join(w["word"] for w in group),
            )
        )
    return segments


def _parse_segments_payload(raw_response: str) -> list[dict]:
    """
    Validator for ollama_client.generate_validated: extract, parse,
    and shape-check the JSON array. Raises ValueError with a SHORT
    reason (it gets fed back to the model) — full detail is logged by
    the caller on final failure.

    Individual entries missing keys are tolerated here (skipped
    downstream in _segments_from_payload) as long as AT LEAST ONE
    entry is well-formed — one garbage segment shouldn't fail the
    whole block, but an all-garbage response should trigger a retry.
    """
    json_str = _extract_json(raw_response)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON ({exc.msg} at position {exc.pos})") from exc

    if not isinstance(parsed, list) or not parsed:
        raise ValueError("expected a non-empty JSON array of segment objects")

    well_formed = 0
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("every segment must be a JSON object")
        if all(
            k in item for k in ("topic", "start_word_index", "end_word_index")
        ):
            well_formed += 1

    if well_formed == 0:
        raise ValueError(
            'no usable segments — every entry needs "topic", '
            '"start_word_index" and "end_word_index"'
        )
    return parsed


def _segments_from_payload(
    payload: list[dict], words: list[WordTimestamp]
) -> list[ConceptSegment]:
    """Convert a validated payload into ConceptSegments.

    Malformed individual entries (out-of-range indices, etc.) are
    clamped/skipped rather than failing the whole block — one bad
    segment shouldn't lose the rest.
    """
    segments: list[ConceptSegment] = []
    for item in payload:
        try:
            start_idx = int(item["start_word_index"])
            end_idx = int(item["end_word_index"])
            start_idx = max(0, min(start_idx, len(words) - 1))
            end_idx = max(start_idx, min(end_idx, len(words) - 1))
            excerpt = " ".join(w["word"] for w in words[start_idx : end_idx + 1])
            segments.append(
                ConceptSegment(
                    topic=str(item["topic"]).strip(),
                    start=words[start_idx]["start"],
                    end=words[end_idx]["end"],
                    transcript_excerpt=excerpt,
                )
            )
        except (KeyError, ValueError, IndexError):
            continue
    return segments


def _segment_via_ollama(words: list[WordTimestamp]) -> list[ConceptSegment]:
    """LLM path: one generate call, with retry-with-correction."""
    word_list_str = _build_word_list_str(words)
    prompt = SEGMENTATION_PROMPT_TEMPLATE.format(word_list=word_list_str)

    retries: list[str] = []

    def _log_retry(attempt: int, reason: str) -> None:
        retries.append(reason)
        print(
            f"[concept_segmenter] attempt {attempt} rejected ({reason}) — "
            "re-prompting with correction..."
        )

    try:
        payload = generate_validated(
            prompt,
            _parse_segments_payload,
            temperature=0.1,  # low temp: structured extraction, not creative
            on_retry=_log_retry,
        )
    except ValueError as exc:
        raise ValueError(
            f"Ollama kept returning unusable output for this dd-block. "
            f"Details: {exc}"
        ) from None

    return _segments_from_payload(payload, words)


def segment_dd_block(words: list[WordTimestamp]) -> list[ConceptSegment]:
    """
    Given the words spoken inside one DD block (already extracted by
    the caller — see dd_processor.py), segment it into concept chunks
    with timestamps.

    Mode comes from config.CONCEPT_SEGMENTATION_MODE:
      "ollama"    — LLM segmentation; falls back to heuristic on
                    connection errors if config.CONCEPT_SEGMENTATION_FALLBACK
      "heuristic" — pause-gap segmentation, no LLM, deterministic

    Raises:
        requests.RequestException: Ollama unreachable AND fallback disabled.
        ValueError: LLM output unusable after retries (mode "ollama",
            fallback only covers connection errors, not garbage output).
    """
    if not words:
        return []

    mode = config.CONCEPT_SEGMENTATION_MODE

    if mode == "heuristic":
        return _heuristic_segment(
            words,
            pause_gap_seconds=config.HEURISTIC_PAUSE_GAP_SECONDS,
            min_segment_words=config.HEURISTIC_MIN_SEGMENT_WORDS,
        )

    if mode != "ollama":
        # Unknown mode string — treat as misconfiguration, fail loud.
        raise ValueError(
            f"CONCEPT_SEGMENTATION_MODE must be 'ollama' or 'heuristic', "
            f"got '{mode}'. Fix config.py or the ONOMA_SEGMENTATION_MODE env var."
        )

    try:
        return _segment_via_ollama(words)
    except requests.RequestException as exc:
        if not config.CONCEPT_SEGMENTATION_FALLBACK:
            raise
        print(
            f"[concept_segmenter] WARNING: Ollama unreachable ({exc.__class__.__name__}). "
            "Falling back to HEURISTIC pause-gap segmentation — topic labels will be "
            "cruder, so expect more asset-match misses. Start Ollama for best results."
        )
        return _heuristic_segment(
            words,
            pause_gap_seconds=config.HEURISTIC_PAUSE_GAP_SECONDS,
            min_segment_words=config.HEURISTIC_MIN_SEGMENT_WORDS,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test concept segmentation on a transcript JSON slice.")
    parser.add_argument("transcript_json", help="Path to a word-level transcript JSON (just the dd-block slice)")
    args = parser.parse_args()

    with open(args.transcript_json, "r", encoding="utf-8") as f:
        test_words = json.load(f)

    result = segment_dd_block(test_words)
    for seg in result:
        print(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.topic}")
        print(f"    \"{seg.transcript_excerpt}\"")
