# Command Vocabulary

## `cut`

Use two `cut` commands to mark one removal span.

```text
... keep this ...
cut
this section is removed
cut
... keep this ...
```

Both spoken command words are removed from the final output.

## `dd`

Use two `dd` commands to mark an explanation block.

```text
... normal speech ...
dd
explain the concept here
and move between related ideas
dd
... normal speech ...
```

The block remains in the video, while its spoken concepts are used to place visual assets.

## Limitation

The parser matches the configured command words literally. Saying `cut` as normal narration can therefore be interpreted as a command. Use a more distinctive command vocabulary later if real recordings show too many false triggers.
