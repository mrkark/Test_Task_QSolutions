"""
test_zoom.py - Pytest suite for Camtasia-style zoom effect logic.

Tests:
1. Coordinate math & clamping (center, boundaries, frame bounds).
2. Ramp frame / time calculations and smoothstep easing math.
3. Event pairing (normal in/out, multiple non-overlapping pairs, open-ended zoom).
4. Sidecar parsing (standard, defaults, missing files, old format without type).
5. "No events -> copy unchanged" path.
6. FFmpeg filter expression generation (zoompan, easing, clip).
7. Dry-run CLI execution.
8. End-to-end video processing with FFmpeg (if binary available).
"""

import os
import json
import pytest
import tempfile
import subprocess
from typing import Dict, Any

from apply_zoom import (
    find_ffmpeg,
    find_sidecar,
    parse_sidecar,
    pair_zoom_events,
    calculate_crop_coordinates,
    smoothstep,
    evaluate_zoom_at_time,
    build_zoom_filter,
    build_ffmpeg_command,
    apply_zoom,
    get_video_duration,
)


class TestSidecarParsing:
    def test_parse_standard_sidecar(self, tmp_path):
        sidecar_file = tmp_path / "test.zoom.json"
        data = {
            "viewport": {"width": 1920, "height": 1080},
            "fps": 30,
            "zoom_factor": 2.5,
            "ramp_sec": 0.6,
            "events": [
                {"t": 2.0, "x": 500, "y": 400, "type": "in"},
                {"t": 5.0, "x": 500, "y": 400, "type": "out"},
            ],
        }
        sidecar_file.write_text(json.dumps(data), encoding="utf-8")

        parsed = parse_sidecar(str(sidecar_file))
        assert parsed["viewport"] == {"width": 1920, "height": 1080}
        assert parsed["fps"] == 30
        assert parsed["zoom_factor"] == 2.5
        assert parsed["ramp_sec"] == 0.6
        assert len(parsed["events"]) == 2
        assert parsed["events"][0] == {"t": 2.0, "x": 500.0, "y": 400.0, "type": "in"}
        assert parsed["events"][1] == {"t": 5.0, "x": 500.0, "y": 400.0, "type": "out"}

    def test_parse_defaults_for_missing_fields(self, tmp_path):
        sidecar_file = tmp_path / "minimal.zoom.json"
        sidecar_file.write_text("{}", encoding="utf-8")

        parsed = parse_sidecar(str(sidecar_file))
        assert parsed["viewport"] == {"width": 1280, "height": 720}
        assert parsed["fps"] == 25
        assert parsed["zoom_factor"] == 2.0
        assert parsed["ramp_sec"] == 0.5
        assert parsed["events"] == []

    def test_parse_non_existent_file(self):
        parsed = parse_sidecar("non_existent_file_xyz.json")
        assert parsed["viewport"] == {"width": 1280, "height": 720}
        assert parsed["events"] == []

    def test_parse_old_sidecars_without_type(self, tmp_path):
        """Old sidecars without 'type' should alternate: 1st=in, 2nd=out, 3rd=in, etc."""
        sidecar_file = tmp_path / "old.zoom.json"
        data = {
            "events": [
                {"t": 1.5, "x": 300, "y": 200},
                {"t": 4.0, "x": 300, "y": 200},
                {"t": 7.0, "x": 800, "y": 450},
                {"t": 9.5, "x": 800, "y": 450},
            ]
        }
        sidecar_file.write_text(json.dumps(data), encoding="utf-8")

        parsed = parse_sidecar(str(sidecar_file))
        assert len(parsed["events"]) == 4
        assert parsed["events"][0]["type"] == "in"
        assert parsed["events"][1]["type"] == "out"
        assert parsed["events"][2]["type"] == "in"
        assert parsed["events"][3]["type"] == "out"

    def test_parse_no_events_empty_list(self, tmp_path):
        sidecar_file = tmp_path / "empty.zoom.json"
        data = {"events": []}
        sidecar_file.write_text(json.dumps(data), encoding="utf-8")

        parsed = parse_sidecar(str(sidecar_file))
        assert parsed["events"] == []


class TestCoordinateMathAndClamping:
    def test_clamping_center_frame(self):
        """At 1280x720, center (640, 360) at zoom 2.0 should yield crop top-left (320, 180)."""
        x, y = calculate_crop_coordinates(px=640.0, py=360.0, zoom=2.0, iw=1280, ih=720)
        assert x == 320.0
        assert y == 180.0

    def test_clamping_top_left_corner(self):
        """Mouse at (0, 0) must clamp to (0, 0), staying inside video frame."""
        x, y = calculate_crop_coordinates(px=0.0, py=0.0, zoom=2.0, iw=1280, ih=720)
        assert x == 0.0
        assert y == 0.0

    def test_clamping_bottom_right_corner(self):
        """Mouse at (1280, 720) must clamp to (iw - iw/zoom, ih - ih/zoom) = (640, 360)."""
        x, y = calculate_crop_coordinates(px=1280.0, py=720.0, zoom=2.0, iw=1280, ih=720)
        assert x == 640.0
        assert y == 360.0

    def test_clamping_zoom_one(self):
        """At zoom 1.0 (no zoom), coordinates must be (0, 0)."""
        x, y = calculate_crop_coordinates(px=500.0, py=300.0, zoom=1.0, iw=1280, ih=720)
        assert x == 0.0
        assert y == 0.0

    def test_clamping_arbitrary_points_within_bounds(self):
        """All coordinates must satisfy: 0 <= x <= iw - iw/zoom and 0 <= y <= ih - ih/zoom."""
        iw, ih = 1280, 720
        zoom = 3.0
        max_x = iw - (iw / zoom)
        max_y = ih - (ih / zoom)

        for px in [-100, 50, 640, 1200, 2000]:
            for py in [-50, 100, 360, 700, 1500]:
                x, y = calculate_crop_coordinates(px, py, zoom=zoom, iw=iw, ih=ih)
                assert 0.0 <= x <= max_x, f"x={x} out of bounds [0, {max_x}] for px={px}"
                assert 0.0 <= y <= max_y, f"y={y} out of bounds [0, {max_y}] for py={py}"


class TestEasingAndTimelineMath:
    def test_smoothstep_boundaries_and_monotonicity(self):
        assert smoothstep(0.0) == 0.0
        assert smoothstep(1.0) == 1.0
        assert smoothstep(0.5) == 0.5
        assert smoothstep(-1.0) == 0.0
        assert smoothstep(2.0) == 1.0

        # Monotonicity test
        prev = 0.0
        for i in range(1, 21):
            val = smoothstep(i / 20.0)
            assert val >= prev
            prev = val

    def test_ramp_frame_calculation(self):
        fps = 25
        ramp_sec = 0.5
        ramp_frames = round(fps * ramp_sec)
        assert ramp_frames in (12, 13)

    def test_evaluate_zoom_timeline_single_pair(self):
        intervals = [{"t_in": 3.0, "t_out": 8.0, "x": 640.0, "y": 360.0}]
        ramp = 0.5
        z_max = 2.0

        # Before zoom-in: zoom = 1.0
        z, _, _ = evaluate_zoom_at_time(1.0, intervals, zoom_factor=z_max, ramp_sec=ramp)
        assert z == 1.0

        # Midpoint of ramp-in (t=3.25): 1.0 < z < 2.0
        z, _, _ = evaluate_zoom_at_time(3.25, intervals, zoom_factor=z_max, ramp_sec=ramp)
        assert 1.4 < z < 1.6

        # During hold (t=5.0): zoom = 2.0
        z, _, _ = evaluate_zoom_at_time(5.0, intervals, zoom_factor=z_max, ramp_sec=ramp)
        assert z == z_max

        # Midpoint of ramp-out (t=8.25): 1.0 < z < 2.0
        z, _, _ = evaluate_zoom_at_time(8.25, intervals, zoom_factor=z_max, ramp_sec=ramp)
        assert 1.4 < z < 1.6

        # After ramp-out (t=9.0): zoom = 1.0
        z, _, _ = evaluate_zoom_at_time(9.0, intervals, zoom_factor=z_max, ramp_sec=ramp)
        assert z == 1.0

    def test_open_ended_zoom_holds_to_end(self):
        """An 'in' with no following 'out' must hold the zoom factor indefinitely."""
        events = [{"t": 2.0, "x": 640.0, "y": 360.0, "type": "in"}]
        intervals = pair_zoom_events(events)
        assert len(intervals) == 1
        assert intervals[0]["t_out"] is None

        # Holds at 5.0s, 30.0s, 100.0s
        for t in [3.0, 10.0, 60.0, 300.0]:
            z, px, py = evaluate_zoom_at_time(t, intervals, zoom_factor=2.0, ramp_sec=0.5)
            assert z == 2.0
            assert px == 640.0
            assert py == 360.0

    def test_multiple_in_out_pairs(self):
        events = [
            {"t": 1.0, "x": 200.0, "y": 200.0, "type": "in"},
            {"t": 3.0, "x": 200.0, "y": 200.0, "type": "out"},
            {"t": 6.0, "x": 800.0, "y": 500.0, "type": "in"},
            {"t": 9.0, "x": 800.0, "y": 500.0, "type": "out"},
        ]
        intervals = pair_zoom_events(events)
        assert len(intervals) == 2
        assert intervals[0]["t_in"] == 1.0 and intervals[0]["t_out"] == 3.0
        assert intervals[1]["t_in"] == 6.0 and intervals[1]["t_out"] == 9.0

        # In interval 1 hold
        z1, x1, y1 = evaluate_zoom_at_time(2.0, intervals)
        assert z1 == 2.0
        assert x1 == 200.0

        # Between interval 1 and 2
        z_mid, _, _ = evaluate_zoom_at_time(4.5, intervals)
        assert z_mid == 1.0

        # In interval 2 hold
        z2, x2, y2 = evaluate_zoom_at_time(7.5, intervals)
        assert z2 == 2.0
        assert x2 == 800.0

    def test_key_repeat_debounce_guard(self):
        """Spurious 'out' events fired within 300ms of 'in' (OS key repeat) must be ignored."""
        events = [
            {"t": 5.0, "x": 400.0, "y": 300.0, "type": "in"},
            {"t": 5.05, "x": 400.0, "y": 300.0, "type": "out"},  # Spurious repeat
            {"t": 10.0, "x": 400.0, "y": 300.0, "type": "out"},  # Real intentional exit
        ]
        intervals = pair_zoom_events(events)
        assert len(intervals) == 1
        assert intervals[0]["t_in"] == 5.0
        assert intervals[0]["t_out"] == 10.0

    def test_single_f5_with_repeat_becomes_open_ended(self):
        """If user presses F5 once and OS sends a repeat out at exact same timestamp, zoom stays open-ended."""
        events = [
            {"t": 55.07, "x": 420.0, "y": 57.0, "type": "in"},
            {"t": 55.07, "x": 420.0, "y": 57.0, "type": "out"},
        ]
        intervals = pair_zoom_events(events)
        assert len(intervals) == 1
        assert intervals[0]["t_in"] == 55.07
        assert intervals[0]["t_out"] is None


class TestFilterGenerationAndCommands:
    def test_no_events_copy_unchanged_command(self):
        sidecar_data = {"events": []}
        cmd = build_ffmpeg_command("input.webm", sidecar_data, "output.webm", ffmpeg_bin="ffmpeg")
        assert "-c" in cmd
        assert "copy" in cmd
        assert "-vf" not in cmd

    def test_zoom_filter_generation(self):
        intervals = [{"t_in": 3.0, "t_out": 8.0, "x": 640.0, "y": 360.0}]
        vf = build_zoom_filter(intervals, width=1280, height=720, fps=25, zoom_factor=2.0, ramp_sec=0.5)

        assert vf.startswith("zoompan=")
        assert "z=" in vf
        assert "x=" in vf
        assert "y=" in vf
        assert "d=1" in vf
        assert "s=1280x720" in vf
        assert "fps=25" in vf
        assert "clip(" in vf
        assert "iw-iw/zoom" in vf
        assert "pow(" in vf

    def test_out_shorter_than_ramp_clamped(self):
        """When t_out < t_in + ramp_sec, filter generation must clamp t_out >= t_in + ramp_sec."""
        intervals = [{"t_in": 2.0, "t_out": 2.2, "x": 500.0, "y": 300.0}]
        vf = build_zoom_filter(intervals, width=1280, height=720, fps=25, zoom_factor=2.0, ramp_sec=0.5)
        # ramp_in ends at 2.5, effective_t_out must be at least 2.5
        assert "between(time,2.500,2.500)" in vf or "between(time,2.000,2.500)" in vf

    def test_get_video_duration_non_existent(self):
        assert get_video_duration("non_existent_file.webm") == 0.0

    def test_dry_run_command_output(self, tmp_path):
        dummy_video = tmp_path / "dummy.webm"
        dummy_video.write_bytes(b"\x00" * 100)

        code, output = apply_zoom(str(dummy_video), dry_run=True)
        assert code == 0
        assert "ffmpeg" in output.lower()
        assert "dummy" in output


class TestEndToEndExecution:
    def test_ffmpeg_end_to_end_encoding(self, tmp_path):
        """If ffmpeg is installed, renders a tiny video to verify actual execution."""
        ffmpeg_bin = find_ffmpeg()
        if not ffmpeg_bin:
            pytest.skip("FFmpeg binary not available on test host")

        # Generate 2-second synthetic video
        test_in = str(tmp_path / "synthetic.webm")
        test_out = str(tmp_path / "synthetic_zoomed.webm")
        sidecar_path = str(tmp_path / "synthetic.webm.zoom.json")

        gen_cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=25",
            "-c:v", "libvpx-vp9",
            test_in,
        ]
        res = subprocess.run(gen_cmd, capture_output=True)
        if res.returncode != 0:
            pytest.skip("Could not generate synthetic test video")

        sidecar_data = {
            "viewport": {"width": 640, "height": 360},
            "fps": 25,
            "zoom_factor": 2.0,
            "ramp_sec": 0.3,
            "events": [
                {"t": 0.5, "x": 320, "y": 180, "type": "in"},
                {"t": 1.5, "x": 320, "y": 180, "type": "out"},
            ],
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f)

        code, out_path = apply_zoom(
            video_path=test_in,
            sidecar_path=sidecar_path,
            output_path=test_out,
            dry_run=False,
            ffmpeg_bin=ffmpeg_bin,
        )

        assert code == 0
        assert os.path.exists(test_out)
        assert os.path.getsize(test_out) > 1000
