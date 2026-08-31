"""
Central configuration for the Onoma Editor pipeline.

Everything tunable lives here so nothing is hardcoded deep in the
pipeline. Adjust these values instead of editing logic in other files.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    """
    Read an optional environment-variable override for a setting.

    Lets you (or a test) flip behavior without editing this file:
        ONOMA_SEGMENTATION_MODE=heuristic python pipeline.py ...
    Only a few behavior switches support this — everything else stays
    a plain constant so the config remains greppable and obvious.
    """
    return os.environ.get(name, default)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
SVG_LIBRARY_DIR = ASSETS_DIR / "svg"
REFERENCE_DIR = ASSETS_DIR / "reference"
TMP_DIR = PROJECT_ROOT / ".tmp"

# ---------------------------------------------------------------------------
# Voice commands
# ---------------------------------------------------------------------------
# The exact spoken word(s) used as commands. Keep these short, distinct
# from normal speech, and unlikely to be said by accident. If "cut" or
# "dd" ever appear naturally in your narration, change these.

CUT_COMMAND_WORD = "cut"
DD_COMMAND_WORD = "dd"

# How close (in seconds) two spoken command words can be to still count
# as a valid start/end pair. Prevents pairing a "cut" from five minutes
# ago with one just spoken by accident.
MAX_COMMAND_PAIR_GAP_SECONDS = 600  # 10 minutes, generous by design

# How much audio padding (seconds) to remove around the spoken command
# word itself, so you don't hear a click or partial word artifact.
COMMAND_WORD_PADDING_SECONDS = 0.15

# ---------------------------------------------------------------------------
# Whisper / transcription
# ---------------------------------------------------------------------------

WHISPER_MODEL_SIZE = "large-v3"  # good accuracy, still local/free via faster-whisper
WHISPER_DEVICE = "cuda"  # change to "cpu" if no NVIDIA GPU available
WHISPER_COMPUTE_TYPE = "float16"  # use "int8" on CPU or lower-VRAM GPUs
WHISPER_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# LLM (Ollama / Gemma) settings
# ---------------------------------------------------------------------------
# MODEL TAGS — verified against https://ollama.com/library/gemma3:
# "Gemma 4 31B" (mentioned during early planning) does not exist. The real
# family is Gemma 3, and ALL sizes (4b / 12b / 27b) are natively
# multimodal (text + image), so one model can serve both text generation
# and any future vision tasks.
#
# Choosing a size (this is YOUR call, Adnan — the default here is a guess):
#   gemma3:4b   — fits easily in ~4 GB VRAM, fastest, weakest at strict-JSON
#                 and at writing clean SVG. Fine for testing the pipeline.
#   gemma3:12b  — ~8-9 GB VRAM, much more reliable structured output.
#                 DEFAULT because it's the best quality/speed tradeoff if
#                 you have a 12 GB+ GPU (RTX 3060 12GB, 4070, etc.).
#   gemma3:27b  — ~17-20 GB VRAM, best quality, needs a 24 GB card
#                 (3090/4090) to run at comfortable speed.
#
# To switch: `ollama pull gemma3:12b` then change OLLAMA_MODEL below.
# If you're unsure what your GPU can hold, start with 12b and drop to 4b
# if you hit out-of-memory errors.

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:12b"  # text generation (segmentation + SVG writing)
OLLAMA_VISION_MODEL = "gemma3:12b"  # all gemma3 sizes are vision-capable
OLLAMA_REQUEST_TIMEOUT_SECONDS = 120

# How many times to re-prompt the LLM when its output fails validation
# (invalid JSON, invalid SVG) before giving up on that one concept.
# Each retry tells the model exactly what was wrong with its last answer.
OLLAMA_MAX_REPAIR_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# Concept segmentation mode
# ---------------------------------------------------------------------------
# "ollama"    — default. Local LLM segments the dd-block into concepts.
#               Best topic labels, which is what drives asset matching.
# "heuristic" — deterministic offline fallback: splits on speech pauses
#               (gap between words), labels topics from the words
#               themselves. Lower quality labels, but works with no
#               Ollama running — useful for tests, planes, and as an
#               automatic fallback (see CONCEPT_SEGMENTATION_FALLBACK).
#               Override without editing this file:
#               ONOMA_SEGMENTATION_MODE=heuristic
CONCEPT_SEGMENTATION_MODE = _env("ONOMA_SEGMENTATION_MODE", "ollama").lower()

# If mode is "ollama" but Ollama is unreachable, fall back to heuristic
# segmentation (with a loud warning) instead of silently losing all
# dd-block visuals. Set False to fail hard instead.
CONCEPT_SEGMENTATION_FALLBACK = True

# Heuristic-mode tuning:
HEURISTIC_PAUSE_GAP_SECONDS = 0.45  # silence gap between words that starts a new concept
HEURISTIC_MIN_SEGMENT_WORDS = 6     # fragments shorter than this merge into the previous concept

# ---------------------------------------------------------------------------
# DD-block visual overlay rendering
# ---------------------------------------------------------------------------
# How SVG diagrams are composited over the screen recording during the
# render stage. PLACEMENT DEFAULT IS A PLACEHOLDER — Adnan hasn't picked
# a final look yet. Options:
#   "bottom_right" (default) — corner overlay, screen recording stays visible
#   "bottom_left", "top_right", "top_left" — other corners
#   "center"       — centered box, screen recording visible around it
#   "full"         — full-screen takeover (scales diagram to fill the frame)
OVERLAY_POSITION = "bottom_right"

# Overlay width as a fraction of the VIDEO width (corner/center modes).
OVERLAY_WIDTH_FRACTION = 0.35

# Gap between the overlay and the frame edge, in pixels (corner/center).
OVERLAY_MARGIN_PX = 48

# Which renderer converts SVG -> PNG before ffmpeg compositing:
#   "auto"      — try cairosvg, then pymupdf, then rsvg-convert (default)
#   "cairosvg"  — pip install cairosvg (Linux/macOS easy; Windows needs
#                 a Cairo/GTK runtime — see README "Windows notes"; renders
#                 fastest and most faithfully)
#   "pymupdf"   — pip install pymupdf (self-contained wheel, no system
#                 libraries — easiest reliable option ON WINDOWS)
#   "rsvg"      — uses the rsvg-convert command-line tool if installed
OVERLAY_RENDER_BACKEND = "auto"

# Render PNGs at this multiple of the SVG's viewBox width, then let
# ffmpeg scale down. Oversampling keeps text crisp after downscaling.
OVERLAY_RENDER_SCALE = 2.0

# ---------------------------------------------------------------------------
# Caption mode
# ---------------------------------------------------------------------------
# "chunk"   — default. One caption line per short word-chunk (current behavior).
# "karaoke" — word-by-word highlighting: every word of the chunk is shown,
#             the currently-spoken word flips to CAPTION_HIGHLIGHT_COLOR.
#             Common in short-form content. Override without editing:
#             ONOMA_CAPTION_MODE=karaoke
CAPTION_MODE = _env("ONOMA_CAPTION_MODE", "chunk").lower()

# Highlight color for the currently-spoken word in karaoke mode.
# Default is the brand green (#3ecf8e) in ASS &HAABBGGRR (BGR!) order.
CAPTION_HIGHLIGHT_COLOR = "&H008ECF3E"

# In karaoke mode, a gap of silence longer than this (seconds) between
# words starts a new caption chunk, so captions break at natural pauses.
CAPTION_BREAK_GAP_SECONDS = 0.6

# ---------------------------------------------------------------------------
# Tavily (reference-only search, never a final asset source)
# ---------------------------------------------------------------------------

TAVILY_API_KEY_ENV_VAR = "TAVILY_API_KEY"  # set this in your .env, never hardcode
TAVILY_MAX_RESULTS = 3
TAVILY_ENABLED = True  # set False to disable and rely only on local assets

# ---------------------------------------------------------------------------
# Caption styling
# ---------------------------------------------------------------------------
# These map to ASS (Advanced SubStation Alpha) subtitle style fields.
# Colors are in &HAABBGGRR hex format (ASS uses BGR, not RGB, and AA is
# alpha where 00 = opaque). Adjust to match your brand look.

CAPTION_FONT_NAME = "Arial Black"
CAPTION_FONT_SIZE = 72
CAPTION_PRIMARY_COLOR = "&H00FFFFFF"   # white text
CAPTION_OUTLINE_COLOR = "&H00000000"   # black outline
CAPTION_BACK_COLOR = "&H00000000"      # transparent-ish background
CAPTION_BOLD = True
CAPTION_OUTLINE_WIDTH = 3
CAPTION_SHADOW = 0
CAPTION_ALIGNMENT = 2  # ASS alignment code: 2 = bottom-center
CAPTION_MARGIN_V = 80  # vertical margin from screen edge, pixels
CAPTION_MAX_WORDS_PER_LINE = 4  # short punchy caption chunks, TikTok-style

# Accent color for emphasized/loud words, if word-level emphasis
# detection is added later (e.g. based on volume or pitch).
CAPTION_EMPHASIS_COLOR = "&H0000CFFF"  # example: orange-ish accent

# ---------------------------------------------------------------------------
# Video output
# ---------------------------------------------------------------------------

OUTPUT_RESOLUTION = "1080x1920"  # reserved: expected final resolution. The pipeline currently renders
                                  # at the INPUT resolution (it does not rescale) — set this correctly if
                                  # you later add a final scale step; overlay sizing uses probed input size.
OUTPUT_FPS = 30
OUTPUT_VIDEO_CODEC = "libx264"
OUTPUT_X264_PRESET = _env("ONOMA_X264_PRESET", "medium")
# "medium" for final uploads; set ONOMA_X264_PRESET=veryfast (or ultrafast)
# for quick draft previews — same output, much faster encode, larger file.
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_CRF = 18  # lower = higher quality, larger file. 18 is visually near-lossless.

# ---------------------------------------------------------------------------
# Asset matching
# ---------------------------------------------------------------------------

ASSET_MATCH_MIN_CONFIDENCE = 0.55  # below this, fall back to SVG generation
ASSET_LIBRARY_INDEX_FILE = SVG_LIBRARY_DIR / "index.json"

# Fuzzy matching for asset lookup (v1.5 — no new dependencies, uses
# difflib). Catches "neurons" vs "neuron", "summation" vs "sums" that
# exact keyword overlap misses. Word pairs must score at least
# ASSET_FUZZY_FLOOR to count at all (kills random low-similarity noise),
# and fuzzy scores are scaled by ASSET_FUZZY_WEIGHT so an exact keyword
# always beats a fuzzy one. Embedding-based matching remains the right
# upgrade once the library is big enough to need it.
ASSET_FUZZY_FLOOR = 0.60
ASSET_FUZZY_WEIGHT = 0.80

# Visual style constraints passed to the SVG generator so generated
# assets match your existing library look. The TEXT-FIT and DISPLAY
# SIZE rules below were added after the first real batch test
# (12 diagrams generated, 2 failed review on exactly these issues —
# labels overflowing their boxes and unreadable-at-overlay-size text).
SVG_STYLE_GUIDE = """
Dark background (near-black, #0a0a0a or transparent).
Thin line weight (1.5-2px strokes), white or light gray (#e0e0e0) lines.
Use ONE consistent stroke width for all similar elements.
Minimal color use — accents only in blue or the brand green #3ecf8e.
Circular nodes for neuron/unit representations, outlined not filled.
Dotted lines to represent uncertain/pending states.
Clean sans-serif labels, small and unobtrusive.
No gradients, no drop shadows, no skeuomorphism.
Overall mood: technical, minimal, moody — not playful or rounded.

TEXT-FIT RULES (non-negotiable):
- Every label must fit inside its container. Estimate text width as
  0.6 x font-size per character; a 120px-wide box fits ~5 chars at
  font-size 34. If it doesn't fit, widen the box or shorten the label
  (e.g. "Attention" -> "Attn", "Feed Forward" -> "FFN").
- Nothing overlaps: boxes don't touch, labels don't touch lines,
  40px+ breathing room between elements.
- Diagrams show at ~378px wide as a corner overlay on 1080p video:
  font-size >= 34 in an 800x600 viewBox, max ~6 text elements,
  labels of 1-3 words.
"""
