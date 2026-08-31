"""
overlay_renderer.py

Bridges dd_processor.py's VisualPlacement list (ORIGINAL-timeline
timestamps + SVG paths) into concrete ffmpeg pieces:

  1. Render each SVG to a transparent PNG (backend: cairosvg, pymupdf,
     or rsvg-convert — see config.OVERLAY_RENDER_BACKEND).
  2. Remap each placement's ORIGINAL-timeline time range into the
     FINAL (post-cut) output timeline. A placement whose span crosses
     a cut or a removed command word becomes MULTIPLE visibility
     windows — handled with a combined `enable` expression.
  3. Build the ffmpeg input args (-loop 1 -t <dur> -i png) and the
     overlay filter chain segment that pipeline.py splices into its
     filter_complex after the caption filter.

Why PNGs instead of feeding SVGs straight to ffmpeg: ffmpeg's native
SVG support is limited/unreliable across builds (and absent in most
Windows builds). Rendering to PNG ourselves is deterministic and gives
us a chance to validate the SVG actually renders before wasting an
encode.

Placement/size policy (config.OVERLAY_POSITION): corner/center modes
scale the diagram to OVERLAY_WIDTH_FRACTION of the video width;
"full" scales it to fill the frame. THE DEFAULT IS A PLACEHOLDER —
Adnan hasn't chosen the final look. Change it in config.py, not here.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import config
from dd_processor import VisualPlacement

# Kept-visible windows shorter than this are dropped — a 2-frame flash
# of a diagram is worse than no diagram.
MIN_WINDOW_SECONDS = 0.05


@dataclass
class TimedOverlay:
    """A rendered PNG plus when (output timeline) it should be visible."""

    png_path: Path
    windows: list[tuple[float, float]]  # [(out_start, out_end), ...]
    topic: str = ""
    source: str = ""


# ---------------------------------------------------------------------------
# SVG -> PNG rendering
# ---------------------------------------------------------------------------

def _render_with_cairosvg(svg_path: Path, png_path: Path, scale: float) -> None:
    import cairosvg  # lazy import — optional dependency

    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), scale=scale)


def _render_with_pymupdf(svg_path: Path, png_path: Path, scale: float) -> None:
    import fitz  # PyMuPDF — lazy import, optional dependency

    doc = fitz.open(str(svg_path))
    try:
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
        pix.save(str(png_path))
    finally:
        doc.close()


def _render_with_rsvg(svg_path: Path, png_path: Path, scale: float) -> None:
    if shutil.which("rsvg-convert") is None:
        raise RuntimeError("rsvg-convert is not on PATH")
    subprocess.run(
        ["rsvg-convert", "--zoom", str(scale), "--output", str(png_path), str(svg_path)],
        check=True,
        capture_output=True,
    )


_RENDER_BACKENDS = {
    "cairosvg": (_render_with_cairosvg, "pip install cairosvg"),
    "pymupdf": (_render_with_pymupdf, "pip install pymupdf"),
    "rsvg": (_render_with_rsvg, "install librsvg's rsvg-convert (e.g. winget / apt / brew)"),
}


def _resolve_backend(preferred: str):
    """
    Return (name, render_fn, install_hint) for the first usable backend.

    Order when preferred == "auto": cairosvg (best fidelity), pymupdf
    (self-contained wheel — the easy reliable option on Windows where
    Cairo DLLs are a pain), rsvg-convert (system tool).
    """
    if preferred != "auto":
        if preferred not in _RENDER_BACKENDS:
            raise ValueError(
                f"OVERLAY_RENDER_BACKEND must be one of "
                f"{sorted(_RENDER_BACKENDS)} or 'auto', got '{preferred}'"
            )
        fn, hint = _RENDER_BACKENDS[preferred]
        if preferred == "rsvg":
            if shutil.which("rsvg-convert") is None:
                raise RuntimeError(
                    f"OVERLAY_RENDER_BACKEND is '{preferred}' but rsvg-convert "
                    f"is not installed. Fix: {hint}"
                )
            return preferred, fn, hint
        return preferred, fn, hint  # import errors surface at render time with context

    for name in ("cairosvg", "pymupdf", "rsvg"):
        fn, hint = _RENDER_BACKENDS[name]
        if name == "cairosvg":
            try:
                import cairosvg  # noqa: F401
                return name, fn, hint
            except ImportError:
                continue
        elif name == "pymupdf":
            try:
                import fitz  # noqa: F401
                return name, fn, hint
            except ImportError:
                continue
        else:
            if shutil.which("rsvg-convert") is not None:
                return name, fn, hint

    raise RuntimeError(
        "No SVG renderer available. Install ONE of:\n"
        "  pip install cairosvg   (best fidelity; Windows needs a Cairo/GTK runtime)\n"
        "  pip install pymupdf    (self-contained wheel — easiest on Windows)\n"
        "  rsvg-convert on PATH   (system package)"
    )


def render_svg_to_png(
    svg_path: str | Path,
    png_path: str | Path,
    scale: float | None = None,
    backend: str | None = None,
) -> Path:
    """
    Render one SVG file to a transparent PNG.

    Raises RuntimeError with actionable install instructions if no
    backend is available, or if the chosen backend fails to render
    (which usually means the SVG itself is broken — the caller decides
    whether to skip that visual or abort).
    """
    svg_path = Path(svg_path)
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    name, fn, hint = _resolve_backend(backend or config.OVERLAY_RENDER_BACKEND)
    try:
        fn(svg_path, png_path, scale or config.OVERLAY_RENDER_SCALE)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"SVG renderer '{name}' failed on {svg_path.name}: {exc}. "
            f"If cairosvg complains about missing Cairo libraries, either "
            f"fix that or {hint}."
        ) from exc
    return png_path


# ---------------------------------------------------------------------------
# Timestamp remapping (original timeline -> post-cut output timeline)
# ---------------------------------------------------------------------------

def compute_output_windows(
    orig_start: float,
    orig_end: float,
    keep_segments: list,
) -> list[tuple[float, float]]:
    """
    Map [orig_start, orig_end] through the keep-segment list into the
    output timeline — the same math pipeline.py applies to caption word
    timestamps, applied here to visual placements.

    A placement entirely inside removed footage returns []. A placement
    straddling a cut returns multiple windows (the pieces that survive).
    Contiguous pieces are merged so one `enable` expression covers them.
    """
    if orig_end <= orig_start:
        return []

    windows: list[tuple[float, float]] = []
    offset = 0.0  # output-timeline position of the current segment's start
    for seg in keep_segments:
        seg_len = seg.end - seg.start
        inter_start = max(orig_start, seg.start)
        inter_end = min(orig_end, seg.end)
        if inter_end - inter_start > 0:
            windows.append(
                (offset + (inter_start - seg.start), offset + (inter_end - seg.start))
            )
        offset += seg_len

    # Merge pieces that are contiguous in the output timeline.
    merged: list[list[float]] = []
    for start, end in windows:
        if end - start < MIN_WINDOW_SECONDS:
            continue
        if merged and start - merged[-1][1] < 0.01:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged if e - s >= MIN_WINDOW_SECONDS]


# ---------------------------------------------------------------------------
# Preparing placements + building ffmpeg pieces
# ---------------------------------------------------------------------------

def prepare_overlays(
    placements: list[VisualPlacement],
    keep_segments: list,
    work_dir: str | Path,
) -> list[TimedOverlay]:
    """
    Render every placement's SVG to a PNG and compute its output-timeline
    visibility windows.

    A placement that renders badly (broken SVG, no backend) is SKIPPED
    with a warning — one bad diagram shouldn't kill the render. A
    placement with no surviving windows (fully inside removed footage)
    is skipped silently — that's expected when a cut eats a dd-block.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    timed: list[TimedOverlay] = []
    for i, placement in enumerate(placements):
        windows = compute_output_windows(placement.start, placement.end, keep_segments)
        if not windows:
            continue

        png_path = work_dir / f"overlay_{i:03d}_{Path(placement.svg_path).stem}.png"
        try:
            render_svg_to_png(placement.svg_path, png_path)
        except RuntimeError as exc:
            print(
                f"[overlay_renderer] WARNING: skipping visual for "
                f"'{placement.topic}' — {exc}"
            )
            continue

        timed.append(
            TimedOverlay(
                png_path=png_path,
                windows=windows,
                topic=placement.topic,
                source=placement.source,
            )
        )
    return timed


def _even(n: float) -> int:
    """Round to the nearest even integer (libx264-friendly dimensions)."""
    v = int(round(n))
    return v if v % 2 == 0 else v + 1


def _placement_expressions(position: str, margin_px: int) -> tuple[str, str]:
    """ffmpeg overlay x/y expressions per position mode.

    W/H = main video dimensions, w/h = overlay dimensions — overlay's
    expression evaluator provides all four, so no hardcoding needed.
    """
    m = margin_px
    positions = {
        "bottom_right": (f"W-w-{m}", f"H-h-{m}"),
        "bottom_left": (f"{m}", f"H-h-{m}"),
        "top_right": (f"W-w-{m}", f"{m}"),
        "top_left": (f"{m}", f"{m}"),
        "center": ("(W-w)/2", "(H-h)/2"),
        "full": ("0", "0"),
    }
    if position not in positions:
        raise ValueError(
            f"OVERLAY_POSITION must be one of {sorted(positions)}, got '{position}'. "
            "Fix config.py."
        )
    return positions[position]


@dataclass
class OverlayChain:
    """Everything pipeline.py needs to splice overlays into its render."""

    input_args: list[str] = field(default_factory=list)   # extra ffmpeg input args
    filter_parts: list[str] = field(default_factory=list)  # filter_graph fragments
    final_label: str = "v0"  # label of the video stream after this chain
    count: int = 0


def build_overlay_chain(
    overlays: list[TimedOverlay],
    video_width: int,
    video_height: int,
    output_duration: float,
    base_label: str = "v0",
    first_input_index: int = 1,
) -> OverlayChain:
    """
    Build the ffmpeg input args + overlay filter chain for all overlays.

    Inputs are added AFTER the main video input, starting at index
    first_input_index (pipeline uses 0 for the video, so default 1).
    Each PNG becomes a `-loop 1 -t <output_duration>` input so frames
    exist for the whole render, and each overlay filter is gated by an
    `enable` expression listing that overlay's visibility windows.

    If two overlays are visible at the same moment, the LATER one in
    the chain draws on top of the earlier one (ffmpeg overlay = paint
    order). Simultaneous overlays shouldn't happen with clean dd-blocks
    — if it ever does, that's a segmentation problem to fix upstream,
    not here.
    """
    if not overlays:
        return OverlayChain(final_label=base_label)

    if output_duration <= 0:
        raise ValueError("output_duration must be positive")

    position = config.OVERLAY_POSITION
    x_expr, y_expr = _placement_expressions(position, config.OVERLAY_MARGIN_PX)

    input_args: list[str] = []
    filter_parts: list[str] = []
    current_label = base_label

    for n, overlay in enumerate(overlays):
        input_index = first_input_index + n

        # Feed each PNG as a looped still-image input bounded to the
        # output duration. `-t` MUST come before `-i` (it's an input
        # option here) or ffmpeg would keep the input open forever.
        input_args.extend(
            ["-loop", "1", "-t", f"{output_duration:.3f}", "-i", str(overlay.png_path)]
        )

        # Scale: corner/center modes target a fraction of the video
        # width (height auto, kept even); "full" fills the frame.
        if position == "full":
            scale_expr = f"scale={_even(video_width)}:{_even(video_height)}"
        else:
            target_w = _even(video_width * config.OVERLAY_WIDTH_FRACTION)
            scale_expr = f"scale={target_w}:-2"

        enable_terms = "+".join(
            f"between(t,{start:.3f},{end:.3f})" for start, end in overlay.windows
        )

        next_label = f"ovl{n}"
        filter_parts.append(
            f"[{input_index}:v]{scale_expr}[ovls{n}];"
            f"[{current_label}][ovls{n}]overlay=x={x_expr}:y={y_expr}"
            f":enable='{enable_terms}'[{next_label}]"
        )
        current_label = next_label

    return OverlayChain(
        input_args=input_args,
        filter_parts=filter_parts,
        final_label=current_label,
        count=len(overlays),
    )
