# Command Vocabulary

## Current commands

| Say this | Meaning |
|---|---|
| "cut" (1st time) | Start of a cut — everything from here gets removed |
| "cut" (2nd time) | End of a cut — everything from the 1st "cut" to here gets removed |
| "dd" (1st time) | Start of an explanation block |
| "dd" (2nd time) | End of an explanation block — visuals get inserted somewhere in this range based on what you say |

Both spoken command words themselves are always removed from the final
audio/video, regardless of command type.

## Known risk: false triggers

Because these are matched as literal spoken words, saying "cut" or "dd"
as normal English (not as a command) will be misread as a command.

- "cut" is a common English word ("let's cut to the chase", "budget
  cuts", etc.) — MODERATE risk of accidental triggers depending on
  your speaking style.
- "dd" is not a normal English word, so LOW risk of accidental
  triggers, but if you ever spell out an abbreviation containing "dd"
  out loud, or reference something like "the dd command" while
  talking about this very project, it could misfire.

### Mitigation options (Adnan's call, not decided here)

1. **Accept the risk** — avoid using these words in normal narration,
   review the warning output from `command_parser.py` after each
   recording (it flags every match and lets you check if a match was
   accidental before rendering).
2. **Switch to more distinctive command words** — e.g. "cutnow" (said
   as one word/no pause) or a made-up word like "onomacut" /
   "onomadd" that will basically never appear by accident. Change
   `CUT_COMMAND_WORD` / `DD_COMMAND_WORD` in `src/config.py`.
3. **Two-word commands** — require a specific two-word phrase (e.g.
   "cut mark") to trigger, which is even less likely to happen by
   accident. Would need a small change to `command_parser.py` to
   match phrases instead of single words — not built yet, flagged in
   AGENT_PROMPT.md as an optional improvement if false triggers turn
   out to be a real problem in practice.

## Recommended workflow

After recording, before running the full pipeline, run just the
parser step and read its output:

```bash
python src/command_parser.py path/to/transcript.json
```

This prints every matched cut span, every matched dd span, and any
warnings (unmatched commands, oddly-spaced pairs, overlaps). Read this
BEFORE spending time on the full render, since a misfired command
here means either lost footage (bad cut) or a missing explanation
visual (bad dd boundary) — cheap to catch here, annoying to catch
after a full render.
