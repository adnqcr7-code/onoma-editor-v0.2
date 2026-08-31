# Agent Handoff Prompt — Onoma Editor

Copy everything below this line into your agent (Claude Code, Manus,
or similar) as the initial task prompt. It's written to stand alone —
the agent should not need this conversation's history to understand
what to do.

---

## Context

You are finishing a project called **Onoma Editor** for Adnan
(GitHub: adnqcr7-code), a solo technical founder who directs AI agents
to build his projects rather than writing all the code himself. He
architects and specs, agents implement. He is time-constrained (school
is starting soon) and needs this tool to actually save him editing
time on his YouTube channel **actual_dev** (creator identity "A9"),
not become another unfinished side project.

Adnan works on Windows, with VS Code, PowerShell, Docker, and Ollama
for local AI. He strongly prefers local/offline-first tools over
cloud/paid APIs where feasible. He has an existing separate project
called **Drama Kingdom** (a different, already-working automated
faceless TikTok pipeline using Piper TTS, Whisper, and ffmpeg) — this
project is NOT that one, it's a new, separate tool specifically for
his actual_dev screen-recording content, but it reuses the same
technical building blocks (Whisper, ffmpeg, local LLM via Ollama) and
you should build in a way that's consistent with that existing stack,
not introduce unnecessary new dependencies.

He also has a separate, earlier-stage project called **Onoma**
(github.com/adnqcr7-code/onoma-video) — a live, timestamped YouTube
transcript tool with a cache-first backend (Node/TypeScript, tRPC,
Drizzle, MySQL). That project explicitly stops before any AI/vision
calls — its own README says "AI layer coming later." This
Onoma Editor project is NOT built on top of that repo directly (this
scaffold is Python-based, that repo is TypeScript-based) — it's a
separate tool that happens to share the "Onoma" name and the general
transcript-first philosophy. If Adnan wants these merged or built as
one system later, that's his call to make explicitly — don't assume
it and don't silently merge them.

## What this tool does, in plain terms

Adnan records himself explaining and building things (voice +
screen recording, no facecam currently) for his actual_dev channel.
Instead of manually editing afterward, he speaks commands INTO the
recording as he talks:

- Say **"cut"**, then later say **"cut"** again — everything between
  those two words (including the words themselves) gets removed from
  the final video. This is how he removes mistakes, retakes, and dead
  air without stopping to edit afterward.
- Say **"dd"**, then later say **"dd"** again — everything between
  those two words is an "explanation block." Inside this block, he
  just explains normally (e.g. "let me explain how a neuron works...
  it sums the inputs... now let's look at layers...") and the system
  should automatically figure out what concepts he's explaining and
  insert relevant visual diagrams (SVGs) at the right moments — WITHOUT
  him tagging each sub-part individually. The natural language of his
  explanation IS the signal (phrases like "this is how X works," "now
  let's look at Y" indicate a new concept starting).
- Captions are auto-generated and burned in, in a style he defines.
- Everything runs as a **post-recording batch pipeline**, not live
  during recording. This was an explicit, deliberate choice — he
  considered live processing and chose post-processing because it's
  simpler to build reliably and produces the identical final result.

## Critical constraints — do not violate these

1. **No web-sourced images as final assets, ever.** Adnan was explicit
   about this. Web search (Tavily) may ONLY be used to give the local
   LLM textual context/inspiration when it's writing new SVG code from
   scratch. It must NEVER be used to fetch an image file and insert it
   into the video directly. See `src/tavily_reference.py` — it
   deliberately only returns text descriptions, never image URLs or
   binary data, and this constraint is documented directly in that
   file's docstring. Do not "simplify" this by making Tavily results
   used directly — that reintroduces licensing risk Adnan specifically
   wanted to avoid.

2. **Everything should run locally/free where possible.** Adnan was
   explicit about not wanting to spend money. Whisper transcription
   (via faster-whisper) runs locally. The LLM (Gemma) runs locally via
   Ollama. Tavily has a free tier and is used sparingly (a few calls
   per video at most, only during dd-block processing, only as
   reference text, not per-frame or per-word). Do not introduce paid
   API dependencies (e.g. OpenAI, Anthropic API, cloud transcription
   services) without flagging this explicitly to Adnan first — it's
   his call, not a default you should make for him.

3. **Adnan's own working style: don't decide for him, lay out
   tradeoffs.** This applies to how you communicate progress and
   decisions back to him too, not just to the AI assistant that helped
   spec this. If you hit a genuine judgment call while building (e.g.
   "should false-trigger risk on the word 'cut' be mitigated by
   changing the command word, or is manual review of warnings
   enough?") — surface it as a choice with tradeoffs, don't just pick
   one silently. Several of these are already flagged inline in the
   code and in `docs/COMMAND_VOCABULARY.md`.

4. **The model name needs verification.** Adnan referred to "Gemma 4
   31B" during planning — this is not a real released model as of
   this build. The closest real model is Gemma 3, which has a 27B
   parameter vision-capable variant. Before doing any real work, run
   `ollama list` and/or check https://ollama.com/library/gemma3 to
   confirm the exact correct model tag, and update
   `OLLAMA_MODEL` / `OLLAMA_VISION_MODEL` in `src/config.py`
   accordingly. Don't silently assume — confirm and tell Adnan what
   you found, since this affects hardware requirements (27B is a large
   model, confirm his GPU can run it at a usable speed, or whether a
   smaller Gemma 3 variant, e.g. 12B or 4B, is a better fit for his
   hardware — ask him what GPU he has if it's not obvious from context).

5. **Windows compatibility.** Adnan works on Windows with PowerShell.
   Test path handling (especially in `caption_generator.py`'s ffmpeg
   filter escaping, which already handles backslash/colon escaping for
   Windows paths, but verify this against a real Windows ffmpeg run)
   and make sure any shell commands you add work in PowerShell, not
   just bash. If you develop/test on a different OS, flag any
   Windows-specific risk you can't personally verify.

## What's already built and verified working

The following modules have been written, and the deterministic parts
have been tested and confirmed working (not just written — actually
run against test fixtures with passing results):

- `src/config.py` — central settings, fully documented
- `src/transcribe.py` — Whisper wrapper, straightforward, standard
  faster-whisper usage
- `src/command_parser.py` — **fully tested, 9/9 tests passing.** Parses
  cut/cut and dd/dd voice command pairs from a transcript, handles
  unmatched commands, overlapping spans, and case/punctuation
  variance. This is the foundation everything else depends on — treat
  changes to this file with extra care and re-run
  `tests/test_command_parser.py` after any edit.
- `src/cut_processor.py` — **verified working** against the sample
  transcript. Converts parsed commands into an ffmpeg-ready keep-segment
  list and filter_complex string. Correctly removes cut spans and
  command words while preserving dd-block content.
- `src/caption_generator.py` — **verified working**, produces valid
  .ass subtitle files from word timestamps.
- `src/pipeline.py` — orchestrates all stages; the cut/caption/render
  path should work end-to-end today given ffmpeg is installed. The
  dd-block visual compositing is NOT yet wired into the final render
  (see "Priority 1" below).

## What's stubbed with real logic and prompts, but needs YOUR work

These are not empty placeholders — they have real implementations,
real prompts, and clear interfaces — but they need iteration against
real data that wasn't available at scaffold-build time (no real
footage, no real asset library, no confirmed Ollama model yet).

### Priority 1: Wire dd-block visuals into the actual render

`dd_processor.py` already computes a full `VisualPlacement` list
(timestamp ranges + SVG paths). `pipeline.py`'s render stage
(`run_pipeline`, Stage 6) currently computes this list but does NOT
yet composite it into the ffmpeg command — there's a `NOTE:` print
statement marking exactly where this needs to happen. You need to:

- Convert each SVG to a transparent PNG overlay (or render at the
  needed size directly) — `rsvg-convert`, `cairosvg`, or ffmpeg's own
  SVG handling (limited) are options; `cairosvg` (Python, pip
  installable) is probably the most reliable cross-platform choice.
- Add `overlay` filters to the ffmpeg filter_complex chain, timed to
  each VisualPlacement's start/end (remember: these timestamps are in
  ORIGINAL video time, and need remapping through
  `_remap_timestamps_after_cuts` the same way captions are, since cuts
  shift everything after them).
- Decide on-screen placement/size for overlays (e.g. corner overlay
  vs full-screen takeover vs picture-in-picture alongside the
  screen-recording) — this is a real design decision Adnan hasn't
  specified yet. Ask him, don't assume, OR ship a sensible default
  (e.g. bottom-right corner, 35% of frame width) clearly marked as
  a placeholder default he can change in `config.py`.

### Priority 2: Confirm and test the Ollama/Gemma integration

Nothing in `concept_segmenter.py` or `svg_generator.py` has been
tested against a real running Ollama instance — these were written
against Ollama's documented API shape but need real verification:

- Confirm the model tag (see constraint #4 above)
- Run `concept_segmenter.py` standalone against a real recorded
  dd-block transcript slice and check whether the concept boundaries
  it produces actually match where Adnan would draw them. Iterate
  the prompt in `SEGMENTATION_PROMPT_TEMPLATE` based on real failures
  — don't guess at improvements, test against real output.
- Run `svg_generator.py` standalone, generate 10-20 test SVGs for
  concepts relevant to Adnan's actual content (AI/coding topics), and
  visually review them (render to PNG and actually look, don't just
  check they're valid XML). Tighten `SVG_STYLE_GUIDE` in
  `config.py` and the prompt template based on what needs fixing —
  common local-LLM SVG failure modes to watch for: overlapping
  elements, text that doesn't fit its container, inconsistent stroke
  widths, ignoring the specified color palette.

### Priority 3: Build out Adnan's real asset library

`assets/svg/` is currently empty except for the index.json format
documented in `docs/ASSET_LIBRARY.md`. This needs Adnan's actual
input — either he provides existing SVGs he's made, or you generate
an initial set with `svg_generator.py` for his most common topics
(based on his past content — AI, LLMs, coding concepts) and he
reviews/approves them before they go in the library for real. Don't
populate this with placeholder/generic content and call it done —
check with him.

### Priority 4: Caption styling

Current caption style in `config.py` is a reasonable generic default,
explicitly NOT Adnan's actual brand style (see
`docs/CAPTION_STYLE.md`). Get real reference examples from him (his
own past videos, or examples he likes) and match fonts/colors/timing
precisely. If he wants word-by-word karaoke-style highlighting
(common in short-form content), this needs a real code change to
`caption_generator.py` — currently it generates one caption line per
word-chunk, not per-word with highlight timing. Flagged in the docs
file, not yet built.

### Priority 5 (lower, optional): Harden edge cases

- `concept_segmenter.py`'s JSON extraction (`_extract_json`) handles
  common local-LLM output quirks (markdown fences, preamble text) but
  hasn't been stress-tested against many real failures. If it fails
  often in practice, consider a retry-with-correction loop (re-prompt
  the model with "your last response wasn't valid JSON, try again"
  rather than just failing).
- `asset_matcher.py` uses simple keyword overlap for matching, which
  is a reasonable v1 but will miss semantically-similar-but-differently
  -worded concepts (e.g. "how a neuron works" vs "single unit
  computation"). An embedding-based similarity search (e.g. using a
  small local embedding model) would be meaningfully better once
  there's a real asset library large enough to make this worthwhile —
  not worth building against an empty/tiny library first.
- Command vocabulary false-trigger risk (see
  `docs/COMMAND_VOCABULARY.md`) — monitor whether "cut" as a normal
  English word causes real problems in practice, and revisit whether
  to switch to more distinctive command words. This is Adnan's
  decision to make based on real experience using the tool, not
  something to preemptively "fix" without his input.

## How to verify your work as you go

- Run `cd src && python -m pytest ../tests/ -v` after any change to
  `command_parser.py`, `cut_processor.py`, or `caption_generator.py`
  — these have real tests and should stay passing.
- For `concept_segmenter.py` and `svg_generator.py`, there are no
  automated tests yet because there was no real Ollama instance or
  real footage available to test against during scaffold creation.
  Your first job with these modules should be writing real tests
  based on what you observe from actual runs, not assuming the
  current prompts are correct.
- Before telling Adnan something is "done," actually run it against
  a real (or realistic sample) recording, not just against the tiny
  synthetic fixture in `tests/sample_transcript.json` — that fixture
  is useful for fast unit testing of parsing logic, but is NOT a
  substitute for testing against real speech patterns, real pacing,
  and real technical vocabulary.

## Communication style Adnan prefers

Be honest and direct about what's actually working vs what's untested
assumption. He explicitly dislikes generic reassurance or glossing
over uncertainty — if something is likely to need rework, say so
clearly rather than presenting it as finished. He's building multiple
ambitious projects solo and directing agents to implement them — he
needs accurate signal about real state, not optimistic status updates.

---

End of handoff prompt.
