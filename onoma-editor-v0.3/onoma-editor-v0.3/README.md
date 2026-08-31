# Onoma Editor

**Post-recording, voice-command video editing for technical content.**

Onoma turns a normal screen recording into an edited video by using spoken commands as edit markers. Record once, then let the pipeline transcribe, cut, caption, add diagrams, and render the final video.

## What it does

### Voice cuts
Say `cut` to start a removal span and `cut` again to end it. The marked footage and the spoken command words are removed.

### Explanation blocks
Say `dd` to start an explanation block and `dd` again to end it. Onoma segments the explanation into concepts, matches them against the local SVG library, and can generate a new SVG when no suitable asset exists.

### Captions
Word-level timestamps are converted into ASS subtitles. `chunk` and `karaoke` modes are supported.

## Pipeline

```text
raw video
  -> faster-whisper transcription
  -> command parsing
  -> cut planning
  -> DD concept segmentation
  -> local asset matching / SVG generation
  -> caption generation
  -> FFmpeg render
  -> final video
```

Everything is designed as a **post-recording** workflow. No live editing is required.

## Repository layout

```text
onoma-editor-v0.2/
├── README.md
├── LICENSE
├── requirements.txt
├── AGENT_PROMPT.md
├── src/
│   ├── asset_matcher.py
│   ├── caption_generator.py
│   ├── command_parser.py
│   ├── concept_segmenter.py
│   ├── config.py
│   ├── cut_processor.py
│   ├── dd_processor.py
│   ├── ollama_client.py
│   ├── overlay_renderer.py
│   ├── pipeline.py
│   ├── svg_generator.py
│   ├── tavily_reference.py
│   └── transcribe.py
├── assets/
│   └── svg/
├── docs/
└── tests/
```

The previous repository layout contained an unnecessary nested `onoma-editor-v0.2/onoma-editor/` directory. This package is flattened so the project files live at the repository root.

## Requirements

- Python 3.10+
- FFmpeg and FFprobe on `PATH`
- Ollama for LLM-driven concept segmentation and SVG generation
- A compatible Gemma model, defaulting to `gemma3:12b`
- `faster-whisper`
- An SVG renderer: CairoSVG or PyMuPDF
- Optional: Tavily API key for text-only reference context

## Install

```powershell
python -m pip install -r requirements.txt
```

Install and start Ollama, then pull the configured model:

```powershell
ollama pull gemma3:12b
```

## Run

```powershell
python src/pipeline.py --input raw_footage.mp4 --output final_video.mp4
```

Useful PowerShell overrides:

```powershell
$env:ONOMA_CAPTION_MODE="karaoke"
$env:ONOMA_SEGMENTATION_MODE="heuristic"
$env:ONOMA_X264_PRESET="veryfast"
python src/pipeline.py --input raw.mp4 --output final.mp4
```

## Testing

```powershell
python -m pytest tests -v
```

The test suite focuses on deterministic components. Real footage, real Whisper output, real Ollama output, and Windows-specific FFmpeg behavior still need validation on the target machine.

## Known limitations

- Literal `cut` and `dd` commands can be false triggers when those words are spoken naturally.
- The default Whisper configuration assumes CUDA. Override the device and compute type for CPU-only systems.
- LLM concept segmentation is probabilistic and should be reviewed with real recordings.
- Generated SVGs are structurally validated, but visual quality still needs human review.
- Output resolution follows the input video. The old `OUTPUT_RESOLUTION` setting has been removed rather than pretending it was active.
- Input media must contain an audio stream because voice commands and transcription depend on audio.

## Security and licensing

Web search is reference-only. Tavily returns text context for generation and is never treated as a final image asset source.

See [`LICENSE`](LICENSE) for the project license.
