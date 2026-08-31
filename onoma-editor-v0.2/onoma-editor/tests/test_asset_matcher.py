"""
Tests for asset_matcher.py — exact, plural, fuzzy, and no-match cases,
plus register/find roundtrip against a temp index.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
from asset_matcher import find_matching_asset, register_asset  # noqa: E402


@pytest.fixture
def temp_index(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({
        "neuron_single.svg": {
            "tags": ["single neuron", "summation", "sigma", "one node", "weighted inputs"],
            "description": "A single neuron summing 4 weighted inputs.",
        },
        "neural_network_full.svg": {
            "tags": ["neural network", "layers", "multiple neurons", "full network"],
            "description": "Multi-layer network.",
        },
        "git_branch.svg": {
            "tags": ["git", "branch", "merge", "commit history"],
            "description": "Git branching diagram.",
        },
    }), encoding="utf-8")
    return index_path


def test_exact_keyword_match(temp_index):
    match = find_matching_asset("neural network layers", index_file=temp_index)
    assert match.asset_path is not None
    assert match.asset_path.name == "neural_network_full.svg"
    assert match.confidence >= config.ASSET_MATCH_MIN_CONFIDENCE


def test_plural_variant_matches(temp_index):
    """'networks' should match the 'network' tag via plural handling."""
    match = find_matching_asset("neural networks", index_file=temp_index)
    assert match.asset_path is not None
    assert match.asset_path.name == "neural_network_full.svg"


def test_fuzzy_match_bridges_word_forms(temp_index):
    """'sums' vs 'summation' — difflib similarity, not exact."""
    match = find_matching_asset("single neuron sums", index_file=temp_index)
    # 'single' and 'neuron' are exact; 'sums' is fuzzy-matched to 'summation'
    assert match.asset_path is not None
    assert match.asset_path.name == "neuron_single.svg"


def test_no_match_below_threshold(temp_index):
    match = find_matching_asset("docker container orchestration", index_file=temp_index)
    assert match.asset_path is None


def test_unrelated_topic_does_not_fuzzy_match(temp_index):
    """Nothing in 'client server model' should reach the confidence bar."""
    match = find_matching_asset("client server model", index_file=temp_index)
    assert match.asset_path is None


def test_exact_beats_fuzzy_across_assets(temp_index):
    """A 3/3-exact-word match must outrank a fuzzy one."""
    match = find_matching_asset("git branch merge", index_file=temp_index)
    assert match.asset_path.name == "git_branch.svg"
    assert match.confidence >= 0.99


def test_register_then_find_roundtrip(tmp_path):
    index_path = tmp_path / "index.json"
    register_asset(
        "attention.svg",
        ["attention", "self attention", "transformer", "query key value"],
        "Attention mechanism diagram.",
        index_file=index_path,
    )
    match = find_matching_asset("transformer attention", index_file=index_path)
    assert match.asset_path is not None
    assert match.asset_path.name == "attention.svg"


def test_empty_index_returns_no_match(tmp_path):
    match = find_matching_asset("anything", index_file=tmp_path / "nonexistent.json")
    assert match.asset_path is None
    assert match.confidence == 0.0


def test_word_similarity_floor_kills_noise():
    from asset_matcher import _word_similarity
    floor = config.ASSET_FUZZY_FLOOR
    assert _word_similarity("neuron", "neuron", floor) == 1.0
    assert _word_similarity("neurons", "neuron", floor) == 0.95
    assert _word_similarity("explain", "summation", floor) == 0.0  # below floor
