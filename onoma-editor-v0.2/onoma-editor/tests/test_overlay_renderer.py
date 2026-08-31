"""
Tests for overlay_renderer.py — timestamp remapping through cuts,
filter-chain construction, and real SVG->PNG rendering via cairosvg.

Requires cairosvg (in requirements) and ffmpeg on PATH for the
dimension-dependent tests. Rendering tests are skipped if cairosvg
is unavailable so the suite stays green on bare machines.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
from cut_processor import KeepSegment  # noqa: E402
from dd_processor import VisualPlacement  # noqa: E402
from overlay_renderer import (  # noqa: E402
    compute_output_windows,
    build_overlay_chain,
    prepare_overlays,
    render_svg_to_png,
    TimedOverlay,
)


def seg(start, end):
    return KeepSegment(start=start, end=end)


def placement(start, end, path="x.svg", topic="topic"):
    return VisualPlacement(
        start=start, end=end, svg_path=Path(path), topic=topic, source="library_match"
    )


# ---------------------------------------------------------------------------
# compute_output_windows — the core cut-remapping math
# ---------------------------------------------------------------------------

def test_window_fully_inside_one_segment():
    keeps = [seg(0, 10), seg(20, 30)]
    # placement 2-5 lives entirely in the first keep segment
    assert compute_output_windows(2.0, 5.0, keeps) == [(2.0, 5.0)]


def test_window_inside_second_segment_shifts_by_removed_time():
    keeps = [seg(0, 10), seg(20, 30)]
    # 20-30 keeps become 10-20 in output; placement 22-25 -> 12-15
    assert compute_output_windows(22.0, 25.0, keeps) == [(12.0, 15.0)]


def test_window_straddling_a_cut_merges_into_continuous_output_window():
    keeps = [seg(0, 10), seg(20, 30)]
    # Placement 8-22 crosses the removed 10-20 region. In the OUTPUT
    # timeline the pieces (8-10 and 10-12) are CONTIGUOUS — the cut
    # glued them together — so they merge into one continuous window.
    # This is correct: the diagram should stay on screen across the
    # splice, not blink.
    windows = compute_output_windows(8.0, 22.0, keeps)
    assert windows == [(8.0, 12.0)]


def test_window_fully_inside_removed_footage_vanishes():
    keeps = [seg(0, 10), seg(20, 30)]
    assert compute_output_windows(12.0, 18.0, keeps) == []


def test_contiguous_pieces_merge():
    # Two back-to-back keep segments: a placement spanning both is one window
    keeps = [seg(0, 10), seg(10, 20)]
    assert compute_output_windows(5.0, 15.0, keeps) == [(5.0, 15.0)]


def test_tiny_windows_dropped():
    keeps = [seg(0, 10), seg(10.0005, 20)]  # sliver of 0.5ms
    windows = compute_output_windows(9.9, 12.0, keeps)
    # the 10.0-10.0005 piece is below MIN_WINDOW_SECONDS and is dropped
    assert all(e - s >= 0.05 for s, e in windows)


# ---------------------------------------------------------------------------
# build_overlay_chain — ffmpeg plumbing
# ---------------------------------------------------------------------------

def _overlay(windows, name="o.png"):
    return TimedOverlay(png_path=Path(name), windows=windows, topic="t")


def test_chain_empty_overlays_is_noop():
    chain = build_overlay_chain([], 1080, 1920, 30.0, base_label="v0")
    assert chain.input_args == []
    assert chain.filter_parts == []
    assert chain.final_label == "v0"
    assert chain.count == 0


def test_chain_builds_inputs_and_filters():
    overlays = [_overlay([(1.0, 3.0)]), _overlay([(5.0, 8.0)])]
    chain = build_overlay_chain(
        overlays, video_width=1080, video_height=1920, output_duration=10.0
    )
    assert chain.count == 2
    # Two extra inputs, each looped and bounded to output duration
    assert chain.input_args[:4] == ["-loop", "1", "-t", "10.000"]
    assert chain.input_args[5] == "o.png"
    assert len(chain.input_args) == 12  # 6 args per input x 2

    # Filters: scale + overlay per input, chained labels
    joined = "".join(chain.filter_parts)
    assert "[1:v]scale=" in joined
    assert "[2:v]scale=" in joined
    assert "overlay=x=" in joined
    assert "enable='between(t,1.000,3.000)'" in joined
    assert "enable='between(t,5.000,8.000)'" in joined
    assert chain.final_label == "ovl1"


def test_chain_multiple_windows_combined_enable():
    overlays = [_overlay([(1.0, 3.0), (7.0, 9.0)])]
    chain = build_overlay_chain(overlays, 1080, 1920, 10.0)
    joined = "".join(chain.filter_parts)
    assert "between(t,1.000,3.000)+between(t,7.000,9.000)" in joined


def test_chain_scale_uses_width_fraction(monkeypatch):
    monkeypatch.setattr(config, "OVERLAY_POSITION", "bottom_right")
    monkeypatch.setattr(config, "OVERLAY_WIDTH_FRACTION", 0.35)
    chain = build_overlay_chain([_overlay([(0, 1)])], 1000, 2000, 10.0)
    assert "scale=350:-2" in "".join(chain.filter_parts)  # 35% of 1000


def test_chain_positions(monkeypatch):
    monkeypatch.setattr(config, "OVERLAY_MARGIN_PX", 40)
    for pos, x_expr, y_expr in [
        ("bottom_right", "W-w-40", "H-h-40"),
        ("bottom_left", "40", "H-h-40"),
        ("top_right", "W-w-40", "40"),
        ("top_left", "40", "40"),
        ("center", "(W-w)/2", "(H-h)/2"),
    ]:
        monkeypatch.setattr(config, "OVERLAY_POSITION", pos)
        chain = build_overlay_chain([_overlay([(0, 1)])], 1080, 1920, 10.0)
        joined = "".join(chain.filter_parts)
        assert f"overlay=x={x_expr}:y={y_expr}" in joined, pos


def test_chain_full_mode_scales_to_frame(monkeypatch):
    monkeypatch.setattr(config, "OVERLAY_POSITION", "full")
    chain = build_overlay_chain([_overlay([(0, 1)])], 1080, 1920, 10.0)
    joined = "".join(chain.filter_parts)
    assert "scale=1080:1920" in joined
    assert "overlay=x=0:y=0" in joined


def test_chain_invalid_position_raises(monkeypatch):
    monkeypatch.setattr(config, "OVERLAY_POSITION", "diagonal")
    with pytest.raises(ValueError, match="OVERLAY_POSITION"):
        build_overlay_chain([_overlay([(0, 1)])], 1080, 1920, 10.0)


def test_chain_zero_duration_raises():
    with pytest.raises(ValueError, match="positive"):
        build_overlay_chain([_overlay([(0, 1)])], 1080, 1920, 0.0)


# ---------------------------------------------------------------------------
# Real rendering (needs cairosvg)
# ---------------------------------------------------------------------------

cairosvg = pytest.importorskip("cairosvg", reason="cairosvg not installed")

TEST_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">
  <rect x="0" y="0" width="800" height="600" fill="none"/>
  <circle cx="200" cy="300" r="80" stroke="#e0e0e0" stroke-width="2" fill="none"/>
  <text x="120" y="320" fill="#3ecf8e" font-size="28">neuron</text>
</svg>"""


def test_render_svg_to_png(tmp_path):
    svg_path = tmp_path / "test.svg"
    svg_path.write_text(TEST_SVG, encoding="utf-8")
    png_path = render_svg_to_png(svg_path, tmp_path / "test.png", backend="cairosvg")
    assert png_path.exists()
    # Oversampled by OVERLAY_RENDER_SCALE (2.0) -> 1600 px wide
    import struct
    with open(png_path, "rb") as f:
        f.read(16)  # PNG signature + IHDR length/type
        width = struct.unpack(">I", f.read(4))[0]
    assert width == 1600


def test_prepare_overlays_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OVERLAY_RENDER_BACKEND", "cairosvg")
    svg_path = tmp_path / "good.svg"
    svg_path.write_text(TEST_SVG, encoding="utf-8")

    keeps = [seg(0, 10), seg(20, 30)]
    placements = [
        placement(2.0, 5.0, svg_path, "concept a"),
        placement(12.0, 18.0, svg_path, "lost to a cut"),
        placement(22.0, 25.0, svg_path, "concept b"),
    ]
    timed = prepare_overlays(placements, keeps, tmp_path / "ovl")
    # Placement 2 fully removed -> dropped; 1 and 3 survive with shifted windows
    assert len(timed) == 2
    assert timed[0].windows == [(2.0, 5.0)]
    assert timed[1].windows == [(12.0, 15.0)]
    assert all(t.png_path.exists() for t in timed)


def test_prepare_overlays_skips_broken_svg(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "OVERLAY_RENDER_BACKEND", "cairosvg")
    # Malformed XML (unclosed <circle>) — reliably unrenderable.
    # Note: cairosvg TOLERATES invalid attribute values (renders them
    # as no-ops), so the fixture must be structurally broken instead.
    bad_svg = tmp_path / "bad.svg"
    bad_svg.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'>"
        "<circle cx='5' cy='5' r='2'></svg>",
        encoding="utf-8",
    )

    keeps = [seg(0, 10)]
    placements = [placement(2.0, 5.0, bad_svg, "broken")]
    timed = prepare_overlays(placements, keeps, tmp_path / "ovl")
    assert timed == []
    assert "WARNING" in capsys.readouterr().out
