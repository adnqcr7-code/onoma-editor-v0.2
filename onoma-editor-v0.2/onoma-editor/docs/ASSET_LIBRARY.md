# Asset Library

Your own SVG/animation assets go in `assets/svg/`. This is the library
the system checks FIRST before generating anything new — the whole
point is that your hand-made assets get reused across videos instead
of regenerating similar visuals every time.

**This library now ships with 12 CANDIDATE assets** (generated at
build time, structurally validated, and visually reviewed — see
`docs/BUILD_NOTES.md`). None are approved yet: review the contact
sheet at `assets/svg/_review/contact_sheet.png`, delete the files you
don't want, and flip the rest to `"status": "approved"` in
index.json (or just delete the `status` field). The pipeline uses
candidates and approved assets equally — the field is bookkeeping for
YOU, so you always know what's been eyeballed.

## Structure

```
assets/svg/
  index.json              <- required, maps filenames to searchable tags
  neuron_single.svg
  neural_network_full.svg
  ... (12 candidates shipped + your future assets)
  _review/                <- rendered previews + contact sheet (generated)
  _candidates/            <- raw generation staging + VLM review results
```

## index.json format

```json
{
  "neuron_single.svg": {
    "tags": ["single neuron", "summation", "sigma", "one node", "weighted sum"],
    "description": "A single neuron with 4 weighted inputs summing into a Σ node, dotted line to a ? output — represents an untrained/undetermined output.",
    "status": "candidate",
    "review": "structural + VLM visual review passed 2026-08-31"
  }
}
```

- `tags`: short phrases someone might use to describe this concept
  when explaining it out loud. Include synonyms and related phrasing —
  the matcher does keyword AND fuzzy matching against these (plural
  variants and close word forms count), so more (relevant) tags =
  better matching. Think about how YOU actually talk about the
  concept, not formal textbook terms.
- `status` (optional): `"candidate"` (generated, not yet approved by
  Adnan) or `"approved"`. Purely informational for the pipeline —
  it matches everything in the index either way. This exists so
  "generated but never reviewed" assets can't silently blend into
  "Adnan approved this look" assets.
- `review` (optional): free-text provenance of when/how it was
  reviewed. Useful when you come back to the library months later.
- `description`: a fuller sentence, used mainly for the SVG generator
  as extra context if it's asked to make something in a similar style
  or extend a concept, and useful for future you to remember what an
  asset actually shows.

## Multi-stage / animated assets

If an asset is meant to build up in stages (like the neuron -> network
progression from the reference image), the current scaffold treats
each SVG as one static visual per concept-segment. For a true
multi-stage reveal (same diagram, progressively adding elements as
you talk through it), you have two options:

1. **Simplest**: make multiple SVG files, one per stage (e.g.
   `nn_stage1_input.svg`, `nn_stage2_layers.svg`,
   `nn_stage3_output.svg`), tag each with its own specific concept
   label, and let concept_segmenter.py's natural segmentation (each
   sub-topic gets its own segment) pick the right stage automatically
   as you move through the explanation.
2. **More advanced**: author a single SVG with labeled/grouped layers
   (e.g. `<g id="stage1">`, `<g id="stage2">`) and extend the renderer
   to reveal groups progressively based on concept segment boundaries.
   Not built in this scaffold — flagged in AGENT_PROMPT.md as a
   worthwhile v2 feature once the basic single-asset-per-segment flow
   is proven to work well.

Option 1 is recommended to start — it requires zero extra code, works
with everything already built, and matches how you described the
Onoma reference image anyway (two related but distinct diagrams).
