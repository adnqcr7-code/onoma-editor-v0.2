"""
tavily_reference.py

STATUS: Working implementation, needs a real TAVILY_API_KEY to test.

IMPORTANT — READ THIS BEFORE MODIFYING:
This module is REFERENCE-ONLY by explicit design decision. It is used
to help svg_generator.py understand what a concept typically looks
like when diagrammed (e.g. "what does a neural network diagram usually
show?"), so the LLM has a better sense of composition and standard
visual conventions when it WRITES ITS OWN SVG CODE.

This module must NEVER:
  - Download and use a web image directly as a final video asset
  - Have its output inserted into the video as-is
  - Bypass svg_generator.py's from-scratch generation

This constraint exists because of image licensing/copyright risk if a
scraped web image ended up in a monetized video, and because Adnan
specifically wants everything code-generated, not sourced. If a future
agent is tempted to "just use the search result image directly" as a
shortcut, don't — that defeats the entire point of this module's
design and reintroduces the exact risk it was built to avoid.
"""

from __future__ import annotations

import os

import requests

from config import TAVILY_API_KEY_ENV_VAR, TAVILY_MAX_RESULTS, TAVILY_ENABLED

TAVILY_API_URL = "https://api.tavily.com/search"


def get_reference_description(concept_topic: str) -> str | None:
    """
    Search for reference material describing how a concept is
    typically diagrammed, and return a short TEXT DESCRIPTION summary
    for svg_generator.py to use as inspiration.

    Returns None if Tavily is disabled, no API key is set, or the
    search fails for any reason — callers must handle None gracefully
    and simply generate SVG without reference context in that case,
    never treat a Tavily failure as a pipeline-blocking error.
    """
    if not TAVILY_ENABLED:
        return None

    api_key = os.environ.get(TAVILY_API_KEY_ENV_VAR)
    if not api_key:
        return None

    try:
        response = requests.post(
            TAVILY_API_URL,
            json={
                "api_key": api_key,
                "query": f"{concept_topic} diagram explanation",
                "search_depth": "basic",
                "max_results": TAVILY_MAX_RESULTS,
                "include_answer": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None

    # Prefer Tavily's synthesized answer if present, otherwise stitch
    # together short snippets from top results. Either way, this stays
    # TEXT — never an image URL, never binary content.
    answer = data.get("answer")
    if answer:
        return str(answer)[:800]

    results = data.get("results", [])
    if results:
        snippets = [r.get("content", "")[:200] for r in results[:2]]
        return " ".join(snippets)

    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Tavily reference lookup for a concept.")
    parser.add_argument("concept", help="Concept to search for reference context on")
    args = parser.parse_args()

    desc = get_reference_description(args.concept)
    if desc:
        print(f"Reference context found:\n{desc}")
    else:
        print("No reference context available (disabled, no API key, or search failed).")
