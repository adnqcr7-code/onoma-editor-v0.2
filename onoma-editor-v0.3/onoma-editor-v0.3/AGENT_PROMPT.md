# Onoma Editor Agent Notes

Onoma Editor is a local-first, post-recording video editor built around three signals:

1. Voice commands (`cut` and `dd`)
2. Word-level transcription
3. Concept-driven visual overlays

Keep the architecture modular. Deterministic parsing and timeline math should not depend on an LLM. LLMs are used only for concept segmentation and SVG generation.

Do not turn Tavily into an image source. It is reference text only.

Before declaring the system production-ready, validate it with real recordings on the target machine and review the rendered output visually.
