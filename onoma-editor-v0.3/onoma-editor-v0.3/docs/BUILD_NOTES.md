# Build Notes

## Fixed in this package

- Flattened the nested repository structure.
- Removed personal names and creator-specific references from the public project files.
- Removed the misleading unused output-resolution setting.
- Added explicit FFmpeg and FFprobe checks.
- Added strict validation for ordered, non-overlapping LLM concept segments.
- Added an explicit audio-stream requirement to the documentation.
- Added a real MIT `LICENSE` file to match the documented license.
- Kept the local/offline-first architecture and text-only Tavily reference flow.

## Still requires target-machine verification

- Real Whisper transcription on recorded speech.
- Real Ollama + Gemma segmentation quality.
- Local Gemma SVG generation quality.
- Windows FFmpeg caption-filter smoke testing.
- Human review of generated diagrams and final caption styling.
