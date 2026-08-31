# Caption Style

All caption styling lives in `src/config.py` under the `CAPTION_*`
settings. Nothing about the caption look is hardcoded in
`caption_generator.py` — change the config, not the logic.

## Current defaults (placeholder, tune to your actual brand)

- Font: Arial Black, 72pt
- White text, black outline, bottom-center placement
- Max 4 words per caption chunk (short, punchy, TikTok-style)

## Caption modes (built)

Two modes, selected via `CAPTION_MODE` in config.py or the
`ONOMA_CAPTION_MODE` env var:

- **`chunk`** (default) — one caption line per short word-chunk. The
  original behavior, clean and simple.
- **`karaoke`** — word-by-word highlighting: the whole chunk stays on
  screen and the currently-spoken word flips to
  `CAPTION_HIGHLIGHT_COLOR` (default: brand green #3ecf8e). Built as
  one Dialogue event per word with inline color overrides — the exact
  approach this doc previously described as "not built here yet".
  Chunk boundaries are pause-aware: a silence gap longer than
  `CAPTION_BREAK_GAP_SECONDS` (0.6s) starts a new chunk, so lines
  break at natural speech boundaries.

Preview either mode without a full render:

```
python src/caption_generator.py transcript.json --output caps.ass --mode karaoke
```

## To match your actual style

You mentioned a dark/moody aesthetic (black, blue, white, green) and
mentioned wanting captions "in the style I want" — the defaults above
are a reasonable generic starting point, NOT your actual brand style,
because that wasn't specified in enough visual detail to encode yet.

To finish this properly, whoever picks up this build (you or an
agent) should:

1. Pull 2-3 reference screenshots of caption styles you like (your own
   past videos, or examples from creators whose caption style you
   want to match).
2. Identify: font, exact colors (hex), whether words highlight/pop as
   they're spoken (karaoke-style), animation (none, pop-in, slide),
   position, and whether there's a background box behind the text or
   just an outline.
3. Update the `CAPTION_*` values in `config.py` accordingly. Karaoke
   highlighting is now built in — set `CAPTION_MODE = "karaoke"` and
   tune `CAPTION_HIGHLIGHT_COLOR`. If you want pop-in/slide animation
   per word, that's still not built (ASS `\t` transform tags would be
   the mechanism) — say the word and an agent can add it.

## ASS color format reminder

ASS uses `&HAABBGGRR` — note this is BGR, not RGB, and reversed from
how you'd normally write a hex color. Double-check any color you pick
from a hex color picker gets converted correctly (swap R and B) or
colors will come out wrong.
