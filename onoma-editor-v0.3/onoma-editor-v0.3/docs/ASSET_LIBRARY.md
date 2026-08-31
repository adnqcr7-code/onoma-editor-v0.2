# Asset Library

Assets live in `assets/svg/` and are indexed by `assets/svg/index.json`.

Each indexed asset should include:

```json
{
  "tags": ["neural network", "layers"],
  "description": "A multi-layer neural network diagram.",
  "status": "candidate"
}
```

Generated assets are written back into the same library so later runs can reuse them.

SVG files are expected to be self-contained and use `viewBox="0 0 800 600"`.
