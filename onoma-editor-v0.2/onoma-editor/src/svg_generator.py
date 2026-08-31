"""
svg_generator.py

STATUS: Real prompt + working call wrapper, NOT yet visually tuned.
Generating SVG that actually looks good and matches Adnan's style
takes iteration against real output — this is explicitly handed off
in AGENT_PROMPT.md as "generate 10-20 test SVGs, review them, tighten
the prompt."

Called when asset_matcher.py finds no good match in the local SVG
library. Uses the local LLM (Gemma via Ollama) to WRITE SVG CODE
directly — not to generate a raster image, and never to fetch an
image from the web. Tavily search (tavily_reference.py) can optionally
be used first to pull a REFERENCE example for the LLM to look at for
inspiration on layout/composition, but the actual output asset is
always freshly written SVG code, so there's no copyright/licensing
risk and everything matches Adnan's existing dark/minimal style.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import config
from ollama_client import generate_validated
from config import (
    SVG_LIBRARY_DIR,
    SVG_STYLE_GUIDE,
)

SVG_GENERATION_PROMPT_TEMPLATE = """You are generating a simple, minimal SVG diagram for an educational coding/AI tutorial video.

CONCEPT TO ILLUSTRATE: {concept_topic}
CONTEXT (what the speaker is saying while this shows on screen): "{transcript_excerpt}"

STYLE REQUIREMENTS (must follow exactly):
{style_guide}

TECHNICAL REQUIREMENTS:
- Output ONLY valid SVG code, starting with <svg and ending with </svg>
- Use viewBox="0 0 800 600" (do not use a fixed width/height attribute, only viewBox, so it scales cleanly)
- No external references (no <image> tags linking to URLs, no external fonts) — everything must be self-contained vector shapes and text
- Keep it simple enough to read in a few seconds on screen — this is not a detailed technical diagram, it's a quick visual aid
- Use <text> elements for any labels, not embedded raster text

{reference_context}

Respond with ONLY the SVG code, no explanation, no markdown code fences."""


def _extract_svg(raw_response: str) -> str:
    """Strip markdown fences or preamble text if the LLM adds them despite instructions."""
    text = raw_response.strip()
    fence_match = re.search(r"```(?:svg|xml)?\s*(<svg.*?</svg>)\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    svg_match = re.search(r"(<svg.*?</svg>)", text, re.DOTALL)
    if svg_match:
        return svg_match.group(1)
    return text


def validate_svg_document(svg_code: str) -> str:
    """
    Structural validation — enough to catch the common local-LLM
    failure modes before an SVG gets anywhere near the render:

      - isn't SVG at all / got cut off mid-generation
      - not well-formed XML (unclosed tags are the classic failure)
      - no viewBox (breaks clean scaling)

    Raises ValueError with a SHORT reason (fed back to the model by
    the retry loop). Returns the svg_code unchanged on success.

    NOTE: this proves the SVG parses, not that it looks good. Visual
    quality (text overflow, overlap, palette) still needs eyeballs —
    render a batch to PNG and actually look at them periodically.
    """
    code = svg_code.strip()
    if not code.startswith("<svg"):
        raise ValueError("response does not start with <svg — output only SVG code")
    try:
        root = ET.fromstring(code)
    except ET.ParseError as exc:
        raise ValueError(f"not well-formed XML ({exc})") from exc
    if not root.tag.lower().endswith("svg"):
        raise ValueError(f"root element is <{root.tag}>, not <svg>")
    if not code.rstrip().endswith("</svg>"):
        raise ValueError("SVG is truncated — it must end with </svg>")
    if "viewBox" not in root.attrib:
        raise ValueError('missing the viewBox attribute (use viewBox="0 0 800 600")')
    return code


def generate_svg(
    concept_topic: str,
    transcript_excerpt: str,
    reference_description: str | None = None,
) -> str:
    """
    Generate new SVG code for a concept with no existing matching asset.

    reference_description: optional text description of a reference
    image found via Tavily (see tavily_reference.py) — used only to
    inform composition/layout, never copied. Pass None to skip.

    Returns raw SVG markup as a string that has passed structural
    validation (well-formed XML, <svg> root, viewBox present). Invalid
    responses trigger up to config.OLLAMA_MAX_REPAIR_ATTEMPTS
    corrective retries before ValueError is raised. Caller is
    responsible for saving it to assets/svg/ and registering it via
    asset_matcher.register_asset() so it's reused next time.
    """
    reference_context = ""
    if reference_description:
        reference_context = (
            f"REFERENCE FOR INSPIRATION (do not copy, use only for layout ideas): "
            f"{reference_description}"
        )

    prompt = SVG_GENERATION_PROMPT_TEMPLATE.format(
        concept_topic=concept_topic,
        transcript_excerpt=transcript_excerpt[:500],  # keep prompt reasonably sized
        style_guide=SVG_STYLE_GUIDE.strip(),
        reference_context=reference_context,
    )

    def _validator(raw_response: str) -> str:
        return validate_svg_document(_extract_svg(raw_response))

    return generate_validated(
        prompt,
        _validator,
        temperature=0.4,  # a bit of creativity is fine here, unlike segmentation
        repair_instruction=(
            "Your previous response was not usable SVG. Respond again with ONLY "
            "one complete, well-formed <svg>...</svg> document with a viewBox "
            'attribute (viewBox="0 0 800 600"). No explanation, no markdown '
            "code fences."
        ),
        on_retry=lambda attempt, reason: print(
            f"[svg_generator] attempt {attempt} rejected ({reason}) — "
            "re-prompting with correction..."
        ),
    )


def save_generated_svg(svg_code: str, filename: str) -> Path:
    """Save generated SVG to the asset library directory."""
    SVG_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SVG_LIBRARY_DIR / filename
    output_path.write_text(svg_code, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a test SVG for a concept.")
    parser.add_argument("concept", help="Concept topic, e.g. 'neural network layers'")
    parser.add_argument("--excerpt", default="", help="Sample transcript excerpt for context")
    parser.add_argument("--output", default="test_generated.svg", help="Output filename")
    args = parser.parse_args()

    svg = generate_svg(args.concept, args.excerpt or args.concept)
    path = save_generated_svg(svg, args.output)
    print(f"Generated -> {path}")
