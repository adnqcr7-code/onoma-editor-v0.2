"""
dd_processor.py

Orchestrates the full DD-block pipeline for one explanation block:

  1. Extract the words spoken within the block's time range
  2. Segment those words into concepts (concept_segmenter.py)
  3. For each concept, try to match a local SVG asset (asset_matcher.py)
  4. If no match, generate a new SVG (svg_generator.py), optionally
     informed by a Tavily reference lookup (tavily_reference.py)
  5. Register any newly generated asset so it's reused next time
  6. Output a final visual placement plan: list of
     (start_time, end_time, svg_path) ready for the renderer

STATUS: The orchestration logic here is complete and should work as
soon as its dependencies (concept_segmenter, asset_matcher,
svg_generator) are tuned against real footage. This file itself needs
minimal changes — it's the pieces it calls that need iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asset_matcher import find_matching_asset, register_asset
from command_parser import CommandSpan
from concept_segmenter import segment_dd_block, ConceptSegment
from config import SVG_LIBRARY_DIR, TAVILY_ENABLED
from svg_generator import generate_svg, save_generated_svg
from tavily_reference import get_reference_description
from transcribe import WordTimestamp


@dataclass
class VisualPlacement:
    start: float
    end: float
    svg_path: Path
    topic: str
    source: str  # "library_match" or "generated"


def _extract_words_in_range(
    all_words: list[WordTimestamp], start: float, end: float
) -> list[WordTimestamp]:
    return [w for w in all_words if start <= w["start"] < end]


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")[:50]


def process_dd_block(
    span: CommandSpan, all_words: list[WordTimestamp]
) -> list[VisualPlacement]:
    """
    Process a single DD block end to end and return the list of visual
    placements to apply during rendering.

    Errors from individual concept processing (e.g. one bad SVG
    generation) should not silently produce an empty result for the
    entire block — see the try/except per-concept below, which skips
    only the failed concept and logs why, so a single failure doesn't
    lose the whole explanation block's visuals.
    """
    block_words = _extract_words_in_range(all_words, span.content_start, span.content_end)
    if not block_words:
        return []

    concepts: list[ConceptSegment] = segment_dd_block(block_words)

    placements: list[VisualPlacement] = []

    for concept in concepts:
        match = find_matching_asset(concept.topic)

        if match.asset_path is not None:
            placements.append(
                VisualPlacement(
                    start=concept.start,
                    end=concept.end,
                    svg_path=match.asset_path,
                    topic=concept.topic,
                    source="library_match",
                )
            )
            continue

        # No good match — generate a new asset
        try:
            reference = None
            if TAVILY_ENABLED:
                reference = get_reference_description(concept.topic)

            svg_code = generate_svg(
                concept_topic=concept.topic,
                transcript_excerpt=concept.transcript_excerpt,
                reference_description=reference,
            )
            filename = f"generated_{_slugify(concept.topic)}.svg"
            saved_path = save_generated_svg(svg_code, filename)

            register_asset(
                filename=filename,
                tags=concept.topic.split(),
                description=f"Auto-generated for concept: {concept.topic}",
            )

            placements.append(
                VisualPlacement(
                    start=concept.start,
                    end=concept.end,
                    svg_path=saved_path,
                    topic=concept.topic,
                    source="generated",
                )
            )
        except Exception as exc:
            # Deliberately non-fatal: one failed generation shouldn't
            # kill the whole block. Surfaced clearly so it's visible
            # during testing/tuning, not silently swallowed.
            print(
                f"[dd_processor] WARNING: failed to produce a visual for "
                f"concept '{concept.topic}' ({concept.start:.1f}s-{concept.end:.1f}s): {exc}"
            )
            continue

    return placements


def process_all_dd_blocks(
    dd_spans: list[CommandSpan], all_words: list[WordTimestamp]
) -> list[VisualPlacement]:
    """Process every DD block in the video and return the combined visual plan."""
    all_placements: list[VisualPlacement] = []
    for span in dd_spans:
        all_placements.extend(process_dd_block(span, all_words))
    return all_placements


if __name__ == "__main__":
    import argparse
    import json

    from command_parser import parse_commands

    parser = argparse.ArgumentParser(description="Process all DD blocks in a transcript into a visual plan.")
    parser.add_argument("transcript_json", help="Path to full word-level transcript JSON")
    args = parser.parse_args()

    with open(args.transcript_json, "r", encoding="utf-8") as f:
        words = json.load(f)

    result = parse_commands(words)
    placements = process_all_dd_blocks(result.dd_spans, words)

    print(f"Generated {len(placements)} visual placement(s):")
    for p in placements:
        print(f"  [{p.start:.1f}s-{p.end:.1f}s] {p.topic} -> {p.svg_path.name} ({p.source})")
