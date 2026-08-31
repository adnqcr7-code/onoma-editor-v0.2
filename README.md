Onoma Editor — Autonomous Voice-Command Video Editor

Onoma Editor is a post-recording video editing pipeline that lets creators control edits using spoken commands while recording.

Instead of manually editing a timeline, you record normally and speak simple commands such as cut and dd. After recording, Onoma processes the footage, removes marked sections, generates captions, and inserts visual assets based on what was said.

Status

The full pipeline is wired end-to-end and has been verified with a real FFmpeg render.

The current pipeline supports:

Voice-command cuts
Karaoke-style captions
DD-block visual overlays
SVG asset matching
Generated SVG fallback assets
One-pass FFmpeg compositing

The included asset library currently contains 12 reviewed candidate SVGs. These are marked as candidate until they are approved for production use.

Some areas still need iteration with real footage:

Concept segmentation quality
SVG generation quality using the local Gemma model
Caption styling and branding
Final asset-library selection

See docs/BUILD_NOTES.md for the current verified build state and remaining work.

Core Idea

Record normally and speak commands directly into the recording.

cut

Say "cut" once to mark the beginning of a section you want removed, then say "cut" again to mark the end.

Everything between the two commands is removed, including the spoken cut commands themselves.

dd

Say "dd" to start an explanation block and say "dd" again to end it.

During a DD block, Onoma analyzes what is being explained and determines which visual assets should appear at each point.

It can:

Segment the explanation into concepts.
Match concepts to the local SVG asset library.
Generate a new SVG when no suitable asset exists.
Insert the resulting visuals at the appropriate timestamps.
Captions

Captions are generated automatically from the word-level transcript and rendered using a configurable style template.

Processing Pipeline
raw_footage.mp4
     |
     v
[1] Whisper transcription
    Word-level timestamps
     |
     v
[2] Command parser
    Finds cut/cut and dd/dd pairs
     |
     v
[3] Cut processor
    Builds FFmpeg trim/concat plan
    Removes spoken commands
     |
     v
[4] DD-block processor
    - Segment transcript into concepts
    - Match concepts to local SVG assets
    - Generate SVG when no match exists
    - Use reference search to inform generation
     |
     v
[5] Caption generator
    Word timestamps -> styled ASS subtitles
     |
     v
[6] FFmpeg renderer
    - Apply cuts
    - Overlay DD visuals
    - Burn captions
     |
     v
final_video.mp4

Everything runs as a post-recording process:

Record → Transcribe → Parse → Cut → Process DD blocks → Generate captions → Render

There is no requirement for live processing during the recording.

Project Structure
onoma-editor/
├── src/
│   ├── transcribe.py
│   ├── command_parser.py
│   ├── cut_processor.py
│   ├── dd_processor.py
│   ├── concept_segmenter.py
│   ├── ollama_client.py
│   ├── asset_matcher.py
│   ├── svg_generator.py
│   ├── overlay_renderer.py
│   ├── caption_generator.py
│   ├── pipeline.py
│   └── config.py
│
├── assets/
│   └── svg/
│       ├── index.json
│       └── ...
│
├── docs/
│   ├── COMMAND_VOCABULARY.md
│   ├── CAPTION_STYLE.md
│   ├── ASSET_LIBRARY.md
│   └── BUILD_NOTES.md
│
├── tests/
├── requirements.txt
└── AGENT_PROMPT.md
Source Modules
Module	Purpose
transcribe.py	Local faster-whisper transcription with word timestamps
command_parser.py	Detects voice commands and builds command pairs
cut_processor.py	Converts commands into FFmpeg keep/remove segments
dd_processor.py	Processes DD blocks and creates visual plans
concept_segmenter.py	Splits explanations into concepts using an LLM or heuristic fallback
ollama_client.py	Shared Ollama client with retry and correction handling
asset_matcher.py	Matches concepts against local SVG assets
svg_generator.py	Generates SVG assets when no suitable match exists
overlay_renderer.py	Converts SVG assets and creates timed FFmpeg overlays
caption_generator.py	Generates chunked or karaoke-style ASS captions
pipeline.py	Orchestrates the complete editing pipeline
config.py	Central configuration and environment settings
Current Capabilities
Command Parser
Detects cut/cut pairs
Detects dd/dd pairs
Handles unmatched commands
Handles nested and overlapping blocks
Handles near-duplicate command words
Fully tested
Cut Processor

Converts parsed commands into an FFmpeg-ready keep/remove plan.

The spoken command words are removed from the final video as well.

Caption Generator

Supports:

Standard chunked captions
Karaoke word-by-word highlighting
Pause-aware caption grouping
Configurable styling
Overlay Renderer

Supports:

SVG-to-PNG rendering
Multiple rendering backends
Timed visual overlays
Timestamp remapping after cuts
FFmpeg compositing
Ollama Integration

Uses a shared Ollama wrapper with:

JSON validation
SVG validation
Retry handling
Automatic correction prompts
Configurable repair attempts
Concept Segmentation

Uses an LLM to identify concepts inside DD blocks.

A deterministic pause-based heuristic fallback is also available, allowing the pipeline to continue when the LLM is unavailable.

Asset Matching

Uses keyword and fuzzy matching to connect spoken concepts with existing assets.

For example:

neurons -> neuron
sums    -> summation
End-to-End Rendering

The complete pipeline can produce a final video containing:

Cuts
Captions
DD visual overlays

These are composited through FFmpeg in a single render pass.

What Still Needs Real-Footage Testing
Concept Segmentation

The segmentation system has been tested against mocked LLM responses.

It still needs testing with real Gemma output to verify that concept boundaries match natural explanations.

SVG Generation

The SVG generation prompt has been refined using a test batch, but generation quality with the local Gemma model still needs real-world evaluation.

Caption Styling

The current caption styling is a generic placeholder.

Production styling should be configured in:

docs/CAPTION_STYLE.md
Asset Library

The included library contains 12 candidate SVG assets.

They currently use:

"status": "candidate"

Assets should be reviewed and approved before being treated as production assets.

See:

docs/ASSET_LIBRARY.md
Reference Search

Tavily integration is available as a reference-only lookup.

Search results are used to inform asset generation and are not directly used as source assets.

A Tavily API key is required to enable this functionality.

Requirements

See requirements.txt for the complete dependency list.

Required
Python 3.10+
FFmpeg installed and available on PATH
Ollama
A compatible Gemma model
faster-whisper
An SVG rendering backend
Recommended

For Ollama:

gemma3:12b

The appropriate model size depends on available hardware. Smaller models can be used for faster processing, while larger models generally provide better concept segmentation and SVG generation.

Optional
Tavily API key for reference searches
Quick Start

Install dependencies:

pip install -r requirements.txt --break-system-packages

Run the complete pipeline:

python src/pipeline.py --input raw_footage.mp4 --output final_video.mp4
Configuration

Most settings can be changed without modifying the source code.

PowerShell
$env:ONOMA_CAPTION_MODE="karaoke"
$env:ONOMA_SEGMENTATION_MODE="heuristic"
$env:ONOMA_X264_PRESET="veryfast"

python src/pipeline.py --input raw.mp4 --output final.mp4
Available Examples

Karaoke captions:

$env:ONOMA_CAPTION_MODE="karaoke"

Disable LLM concept segmentation:

$env:ONOMA_SEGMENTATION_MODE="heuristic"

Use a faster FFmpeg preset for draft renders:

$env:ONOMA_X264_PRESET="veryfast"
Testing

The project includes a test suite covering the core processing components.

Run:

cd src
python -m pytest ../tests/ -v
Windows Notes

Onoma is designed to work with Windows and uses subprocess argument lists rather than shell-specific command strings.

SVG Rendering

CairoSVG may require a Cairo runtime on Windows.

If CairoSVG produces DLL errors, PyMuPDF can be used as an alternative rendering backend:

pip install pymupdf

Then configure:

OVERLAY_RENDER_BACKEND = "pymupdf"

The PyMuPDF path is implemented but should be verified on the target Windows environment.

FFmpeg Captions

Windows drive-letter path escaping is handled by the caption filter builder.

A real Windows FFmpeg smoke test is still recommended before production use.

Documentation

Additional documentation is available in the docs/ directory:

COMMAND_VOCABULARY.md — Voice command specification
CAPTION_STYLE.md — Caption styling and karaoke configuration
ASSET_LIBRARY.md — SVG asset organization and approval
BUILD_NOTES.md — Build verification and remaining work
Architecture

Onoma is intentionally designed as a post-production automation pipeline rather than a live editor.

The goal is to make recording feel natural while moving the complexity of editing into an automated processing stage.

                 ┌─────────────────┐
                 │    Recording    │
                 │  Voice + Video  │
                 └────────┬────────┘
                          │
                          v
                 ┌─────────────────┐
                 │   Transcribe    │
                 │    Whisper      │
                 └────────┬────────┘
                          │
                          v
                 ┌─────────────────┐
                 │ Parse Commands  │
                 │ cut / dd / ...  │
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              v                       v
       ┌──────────────┐        ┌──────────────┐
       │ Cut Processor│        │ DD Processor │
       └──────┬───────┘        └──────┬───────┘
              │                       │
              │                ┌──────┴──────┐
              │                │   Concept   │
              │                │ Segmentation│
              │                └──────┬──────┘
              │                       │
              │                ┌──────┴──────┐
              │                │Asset Matcher│
              │                └──────┬──────┘
              │                       │
              │                ┌──────┴──────┐
              │                │SVG Generator│
              │                └──────┬──────┘
              │                       │
              └───────────┬───────────┘
                          v
                 ┌─────────────────┐
                 │    Captions     │
                 └────────┬────────┘
                          │
                          v
                 ┌─────────────────┐
                 │     FFmpeg      │
                 │ Final Composite │
                 └────────┬────────┘
                          │
                          v
                 ┌─────────────────┐
                 │ final_video.mp4 │
                 └─────────────────┘
License

Add the project's license here when one has been selected.
