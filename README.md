# Onoma Editor — Autonomous Voice-Command Video Editor

Built for actual_dev / A9 content: voice + screen recordings, edited by
speaking commands during the take instead of manual timeline editing.

## Status

**The full pipeline is now wired end-to-end and verified with a real
ffmpeg render** (see `docs/BUILD_NOTES.md` for exactly what was tested
and what still needs real-footage iteration). Cuts, karaoke captions,
and dd-block visual overlays all composite in a single ffmpeg pass.
An initial asset library of 12 reviewed candidate SVGs ships with the
project — marked `status: candidate` until Adnan approves them.

The pieces that still need iteration against REAL footage (not
synthetic tests): concept segmentation prompt quality, SVG generation
quality from the local Gemma model, and caption styling to match
Adnan's actual brand look.

See `AGENT_PROMPT.md` for the original handoff brief and
`docs/BUILD_NOTES.md` for the current build state (what an agent did,
what's verified vs. assumed).

## Core idea

You record normally and speak commands inline:

- Say **"cut"** once to mark the start of a cut, **"cut"** again to mark
  the end. Everything between (including both spoken "cut"s) is removed.
- Say **"dd"** once to start an explanation block, **"dd"** again to end
  it. Inside that block, the system reads what you're saying and matches
  your explanation to visual assets (your own SVGs/animations, or
  generates new ones in your style) and inserts them at the right
  moments.
- Captions are auto-generated from the transcript and burned in using a
  style template you define once.

No live processing. Everything runs as a **post-recording pass**:
record → transcribe → parse commands → process cuts → process dd-blocks
→ burn captions → render final video.

## Pipeline stages

```
raw_footage.mp4
     |
     v
[1] Whisper transcription (word-level timestamps)
     |
     v
[2] Command parser (finds cut/cut and dd/dd pairs + timestamps)
     |
     v
[3] Cut processor (builds ffmpeg trim list, removes spoken commands too)
     |
     v
[4] DD-block processor (per block):
       - segment transcript into concepts (LLM)
       - match each concept to local SVG asset library
       - fallback: generate new SVG in-style if no match
       - reference search (Tavily) used only to inform generation,
         never as a source asset
     |
     v
[5] Caption generator (word-level timestamps -> styled ASS subtitles)
     |
     v
[6] Render (ffmpeg: apply cuts, overlay dd-block visuals at their
    timestamps, burn captions)
     |
     v
final_video.mp4
```

## Directory layout

```
onoma-editor/
  src/
    transcribe.py          # Whisper wrapper, word-level timestamps
    command_parser.py       # finds cut/cut, dd/dd pairs -> command list
    cut_processor.py        # command list -> ffmpeg trim/concat plan
    dd_processor.py         # dd-block -> concept segments -> asset plan
    concept_segmenter.py    # LLM (Gemma via Ollama) segmentation + heuristic fallback
    ollama_client.py        # shared Ollama call wrapper + retry-with-correction
    asset_matcher.py        # matches concepts to local SVG library (keyword + fuzzy)
    svg_generator.py        # generates new SVG in-style when no match (+ validation)
    overlay_renderer.py     # SVG -> PNG + timed ffmpeg overlay filter chain
    caption_generator.py    # transcript -> styled ASS subtitles (chunk or karaoke)
    pipeline.py              # orchestrates all stages end to end
    config.py                # all tunable settings in one place
  assets/
    svg/                      # asset library: 12 candidate SVGs + index.json
  docs/
    COMMAND_VOCABULARY.md    # exact spoken command spec
    CAPTION_STYLE.md          # how to define your caption look (incl. karaoke)
    ASSET_LIBRARY.md          # how to organize your SVG library
    BUILD_NOTES.md            # current build state: verified vs. untested
  tests/                      # 82 tests — run: cd src && python -m pytest ../tests/ -v
  requirements.txt
  AGENT_PROMPT.md            # long handoff brief for an agent to finish this
```

## What's fully working right now

- `command_parser.py` — parses cut/cut and dd/dd pairs from a Whisper
  transcript, handles edge cases (unmatched commands, nested/overlapping
  blocks, near-duplicate command words), fully tested.
- `cut_processor.py` — turns a command list into an ffmpeg-ready
  keep/remove segment list, including removing the spoken command
  words themselves.
- `caption_generator.py` — chunk mode AND karaoke (word-by-word
  highlight) mode, pause-aware chunking, fully configurable via
  `config.py`.
- `overlay_renderer.py` — renders library SVGs to PNG (cairosvg /
  PyMuPDF / rsvg-convert) and composites them as timed overlays,
  with timestamps correctly remapped through cuts.
- `ollama_client.py` — one shared Ollama wrapper with a
  retry-with-correction loop (bad JSON / bad SVG gets re-prompted with
  the reason it was rejected, up to `OLLAMA_MAX_REPAIR_ATTEMPTS`).
- `concept_segmenter.py` — LLM segmentation via Ollama, PLUS a
  deterministic heuristic fallback (pause-gap based) so a dead Ollama
  degrades the pipeline instead of breaking it.
- `asset_matcher.py` — keyword + fuzzy matching ("neurons" ~
  "neuron", "sums" ~ "summation") with a tunable noise floor.
- `pipeline.py` — the WHOLE thing renders in one ffmpeg pass: cuts,
  captions, and dd-block overlays.
- `transcribe.py` — thin wrapper around faster-whisper for local,
  free, word-level transcription.

## What still needs real-footage iteration

- `concept_segmenter.py` prompt quality — tested against mocked
  responses only; real Gemma output needs checking against where
  Adnan would actually draw concept boundaries.
- `svg_generator.py` — the prompt is tightened from a real 12-diagram
  test batch, but local-Gemma SVG quality is untested (the candidate
  library was generated by a stronger hosted model at build time).
- Caption styling is still the generic placeholder — needs Adnan's
  real brand fonts/colors (see `docs/CAPTION_STYLE.md`).
- Asset library — 12 candidates shipped, all marked `status:
  "candidate"`; needs Adnan's approval (see `docs/ASSET_LIBRARY.md`).
- Tavily integration — wired as a reference-only lookup, not an asset
  source. Needs your API key in `.env`.

## Requirements

See `requirements.txt`. Summary: Python 3.10+, ffmpeg installed and on
PATH, Ollama running locally with a Gemma 3 model pulled (`gemma3:12b`
recommended — see config.py for the 4b/12b/27b tradeoff),
faster-whisper, cairosvg (or PyMuPDF) for SVG rendering, and optionally
a Tavily API key (free tier is fine, used sparingly).

## Quick start (once dependencies are installed)

```bash
pip install -r requirements.txt --break-system-packages
python src/pipeline.py --input raw_footage.mp4 --output final_video.mp4
```

Useful env-var switches (no code edits needed):

```powershell
# PowerShell, Windows
$env:ONOMA_CAPTION_MODE="karaoke"      # word-by-word highlight captions
$env:ONOMA_SEGMENTATION_MODE="heuristic" # no-LLM fallback segmentation
$env:ONOMA_X264_PRESET="veryfast"        # fast draft renders
python src/pipeline.py --input raw.mp4 --output final.mp4
```

## Windows notes

- Everything is PowerShell-safe (subprocess lists, no bash-isms).
- cairosvg needs a Cairo runtime on Windows — if `pip install cairosvg`
  gives DLL errors, `pip install pymupdf` instead and set
  `OVERLAY_RENDER_BACKEND = "pymupdf"` in config.py (self-contained
  wheel, no system libraries). This path is implemented but was NOT
  tested on a real Windows machine — verify on yours.
- The caption filter path-escaping for Windows drive letters is
  implemented (`build_ffmpeg_caption_filter`) but deserves a real
  Windows ffmpeg smoke test.
