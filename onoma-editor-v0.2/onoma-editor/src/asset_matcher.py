"""
asset_matcher.py

STATUS: Scaffolded with working keyword-matching logic. Embedding-based
semantic matching (better quality) is stubbed and documented — needs a
real asset library to test against before it's worth building out
fully, since there's nothing to match against yet. See AGENT_PROMPT.md.

Given a concept label (e.g. "neural network layers") from
concept_segmenter.py, finds the best-matching SVG asset in Adnan's
local library (assets/svg/), or reports no match so the caller can
fall back to svg_generator.py.

Asset library format expected (see docs/ASSET_LIBRARY.md):

assets/svg/
  index.json          <- maps asset filenames to descriptive tags
  neuron_single.svg
  neural_network_full.svg
  ...

index.json format:
{
  "neuron_single.svg": {
    "tags": ["single neuron", "summation", "sigma", "one node"],
    "description": "A single neuron with 4 inputs summing into a Σ node, dotted line to a ? output."
  },
  "neural_network_full.svg": {
    "tags": ["neural network", "layers", "multiple neurons", "full network"],
    "description": "Multi-layer network of neurons connecting through to a checkmark output."
  }
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import config
from config import SVG_LIBRARY_DIR, ASSET_LIBRARY_INDEX_FILE


@dataclass
class AssetMatch:
    asset_path: Path | None
    confidence: float
    matched_tags: list[str]


def _load_asset_index(index_file: Path | None = None) -> dict:
    path = index_file or ASSET_LIBRARY_INDEX_FILE
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _word_similarity(a: str, b: str, floor: float) -> float:
    """
    Similarity of two lowercase words, 0.0-1.0.

      identical            -> 1.0
      plural variants      -> 0.95  ("neurons" vs "neuron")
      sequence similarity  -> difflib ratio, but ONLY if it clears the
                              floor — below-floor pairs return 0 so noise
                              like "explain" vs "summation" can't
                              accumulate into a fake match

    Deliberately NOT stemming beyond a trailing 's' (Porter stemming
    would help a little but adds behavior nobody can eyeball). When
    this stops being enough, the right next step is embedding
    similarity, not more string heuristics — see AGENT_PROMPT.md.
    """
    if a == b:
        return 1.0
    if len(a) > 2 and len(b) > 2 and a.rstrip("s") == b.rstrip("s"):
        return 0.95
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= floor else 0.0


def _match_score(
    concept_topic: str, tags: list[str]
) -> tuple[float, list[str]]:
    """
    Score how well an asset's tags cover a concept topic.

    For each word in the concept topic, take its best similarity
    against ANY word in ANY tag (fuzzy scores scaled by
    ASSET_FUZZY_WEIGHT so exact keyword hits always outrank fuzzy
    ones), then average over the topic's words. Tags with at least one
    non-zero word match are reported as matched_tags.

    This is v1.5: keyword-overlap (v1) + light fuzzy matching. It
    still misses true synonyms ("how a neuron works" vs "single unit
    computation") — that needs embedding-based similarity, worth
    building only once the library is big enough for the misses to
    hurt. See AGENT_PROMPT.md, "Upgrade asset_matcher.py".
    """
    concept_words = [w for w in concept_topic.lower().split() if w]
    if not concept_words:
        return 0.0, []

    floor = config.ASSET_FUZZY_FLOOR
    weight = config.ASSET_FUZZY_WEIGHT

    tag_word_sets: list[tuple[str, set[str]]] = [
        (tag, {w for w in tag.lower().split() if w}) for tag in tags
    ]

    total = 0.0
    matched_tags: list[str] = []
    for concept_word in concept_words:
        best = 0.0
        best_tag = None
        for tag, tag_words in tag_word_sets:
            if not tag_words:
                continue
            tag_best = max(_word_similarity(concept_word, tw, floor) for tw in tag_words)
            score = tag_best if tag_best >= 1.0 else tag_best * weight
            if score > best:
                best = score
                best_tag = tag
        total += best
        if best_tag is not None and best_tag not in matched_tags:
            matched_tags.append(best_tag)

    return total / len(concept_words), matched_tags


def find_matching_asset(
    concept_topic: str, index_file: Path | None = None
) -> AssetMatch:
    """
    Find the best-matching local SVG asset for a given concept label.

    index_file is injectable for tests; production callers leave it
    None and get config.ASSET_LIBRARY_INDEX_FILE.

    Returns AssetMatch with asset_path=None if nothing meets
    ASSET_MATCH_MIN_CONFIDENCE — the caller (dd_processor.py) should
    fall back to svg_generator.py in that case.
    """
    index = _load_asset_index(index_file)
    if not index:
        return AssetMatch(asset_path=None, confidence=0.0, matched_tags=[])

    best_score = 0.0
    best_filename = None
    best_matched_tags: list[str] = []

    for filename, meta in index.items():
        tags = meta.get("tags", [])
        score, matched_tags = _match_score(concept_topic, tags)
        if score > best_score:
            best_score = score
            best_filename = filename
            best_matched_tags = matched_tags

    if best_score < config.ASSET_MATCH_MIN_CONFIDENCE or best_filename is None:
        return AssetMatch(asset_path=None, confidence=best_score, matched_tags=[])

    library_dir = index_file.parent if index_file else SVG_LIBRARY_DIR
    return AssetMatch(
        asset_path=library_dir / best_filename,
        confidence=best_score,
        matched_tags=best_matched_tags,
    )


def register_asset(
    filename: str,
    tags: list[str],
    description: str,
    index_file: Path | None = None,
) -> None:
    """
    Add a new asset to the index — call this after svg_generator.py
    creates a new SVG, so it becomes reusable next time instead of
    regenerating the same concept repeatedly.
    """
    target = index_file or ASSET_LIBRARY_INDEX_FILE
    index = _load_asset_index(target)
    index[filename] = {"tags": tags, "description": description}
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test asset matching for a concept label.")
    parser.add_argument("concept", help="Concept topic label to search for, e.g. 'neural network layers'")
    args = parser.parse_args()

    match = find_matching_asset(args.concept)
    if match.asset_path:
        print(f"MATCH: {match.asset_path} (confidence {match.confidence:.2f})")
        print(f"  matched tags: {match.matched_tags}")
    else:
        print(f"NO MATCH (best confidence {match.confidence:.2f}, below threshold {ASSET_MATCH_MIN_CONFIDENCE})")
        print("  -> caller should fall back to svg_generator.py")
