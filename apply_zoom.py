#!/usr/bin/env python3
"""
apply_zoom.py - Camtasia-style zoom effect post-processor using FFmpeg zoompan.

Reads video recording and optional sidecar JSON (<video>.zoom.json), then
renders a smooth zoom-in -> hold -> zoom-out effect centered at recorded mouse coordinates.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from typing import Optional, Dict, Any, List, Tuple


def find_ffmpeg(custom_path: Optional[str] = None) -> str:
    """Finds ffmpeg executable on PATH, from custom path, or from imageio_ffmpeg."""
    if custom_path:
        if os.path.exists(custom_path):
            return os.path.abspath(custom_path)
        which_custom = shutil.which(custom_path)
        if which_custom:
            return which_custom
        raise FileNotFoundError(f"Custom ffmpeg binary not found at: {custom_path}")

    # Check system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    # Check imageio_ffmpeg fallback if installed
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass

    # Default fallback
    return "ffmpeg"


def find_sidecar(video_path: str, explicit_sidecar: Optional[str] = None) -> Optional[str]:
    """Locates the sidecar json file for the given video."""
    if explicit_sidecar:
        if os.path.exists(explicit_sidecar):
            return os.path.abspath(explicit_sidecar)
        raise FileNotFoundError(f"Explicit sidecar file not found: {explicit_sidecar}")

    candidates = [
        f"{video_path}.zoom.json",
        f"{os.path.splitext(video_path)[0]}.zoom.json",
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None


def parse_sidecar(sidecar_path: Optional[str], default_fps: int = 25, default_zoom: float = 2.0, default_ramp: float = 0.5) -> Dict[str, Any]:
    """
    Parses a sidecar JSON file.
    Supports standard sidecars, missing defaults, old sidecars without 'type',
    and empty event lists.
    """
    data = {
        "viewport": {"width": 1280, "height": 720},
        "fps": default_fps,
        "zoom_factor": default_zoom,
        "ramp_sec": default_ramp,
        "events": [],
    }

    if not sidecar_path or not os.path.exists(sidecar_path):
        return data

    with open(sidecar_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        return data

    if "viewport" in loaded and isinstance(loaded["viewport"], dict):
        data["viewport"]["width"] = int(loaded["viewport"].get("width", 1280))
        data["viewport"]["height"] = int(loaded["viewport"].get("height", 720))

    data["fps"] = int(loaded.get("fps", default_fps))
    data["zoom_factor"] = float(loaded.get("zoom_factor", default_zoom))
    data["ramp_sec"] = float(loaded.get("ramp_sec", default_ramp))

    raw_events = loaded.get("events", [])
    normalized_events = []

    # Handle old sidecars without 'type' (alternating in -> out -> in -> out)
    for idx, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            continue
        t = float(ev.get("t", 0.0))
        x = float(ev.get("x", data["viewport"]["width"] / 2.0))
        y = float(ev.get("y", data["viewport"]["height"] / 2.0))
        ev_type = ev.get("type")
        if not ev_type:
            ev_type = "in" if (idx % 2 == 0) else "out"
        normalized_events.append({"t": t, "x": x, "y": y, "type": ev_type.lower()})

    data["events"] = normalized_events
    return data


def pair_zoom_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Pairs each 'in' with the next 'out':
    - Zoom-in (ramp) -> hold (user-controlled) -> zoom-out (ramp)
    - If an 'in' has no following 'out', hold the zoom to the end of the video (open-ended zoom).
    """
    intervals = []
    current_in = None

    for ev in events:
        ev_type = ev.get("type", "in")
        if ev_type == "in":
            if current_in is not None:
                # Previous 'in' had no 'out' before this 'in'; close previous as open-ended
                intervals.append({
                    "t_in": current_in["t"],
                    "t_out": None,
                    "x": current_in["x"],
                    "y": current_in["y"],
                })
            current_in = ev
        elif ev_type == "out":
            if current_in is not None:
                intervals.append({
                    "t_in": current_in["t"],
                    "t_out": ev["t"],
                    "x": current_in["x"],
                    "y": current_in["y"],
                })
                current_in = None
            else:
                # 'out' without preceding 'in'; ignore
                pass

    if current_in is not None:
        intervals.append({
            "t_in": current_in["t"],
            "t_out": None,
            "x": current_in["x"],
            "y": current_in["y"],
        })

    return intervals


def calculate_crop_coordinates(px: float, py: float, zoom: float, iw: int, ih: int) -> Tuple[float, float]:
    """
    Calculates top-left (x, y) coordinates for FFmpeg zoompan filter so zoom
    centers on mouse point (px, py) and stays strictly within bounds:
        x = clamp(px - iw/(2*zoom), 0, iw - iw/zoom)
        y = clamp(py - ih/(2*zoom), 0, ih - ih/zoom)
    """
    if zoom <= 1.0:
        return 0.0, 0.0

    max_x = max(0.0, iw - (iw / zoom))
    max_y = max(0.0, ih - (ih / zoom))
    raw_x = px - (iw / (2.0 * zoom))
    raw_y = py - (ih / (2.0 * zoom))

    x = max(0.0, min(max_x, raw_x))
    y = max(0.0, min(max_y, raw_y))
    return x, y


def smoothstep(p: float) -> float:
    """Standard smoothstep easing: 3*p^2 - 2*p^3 for p in [0, 1]."""
    p_clamped = max(0.0, min(1.0, p))
    return p_clamped * p_clamped * (3.0 - 2.0 * p_clamped)


def evaluate_zoom_at_time(t: float, intervals: List[Dict[str, Any]], zoom_factor: float = 2.0, ramp_sec: float = 0.5) -> Tuple[float, float, float]:
    """
    Evaluates (zoom, target_x, target_y) for a specific time t.
    Useful for unit testing and frame verification.
    """
    if not intervals:
        return 1.0, 0.0, 0.0

    current_zoom = 1.0
    active_px = 0.0
    active_py = 0.0

    for item in intervals:
        t_in = item["t_in"]
        t_out = item["t_out"]
        px = item["x"]
        py = item["y"]

        ramp_in_end = t_in + ramp_sec

        if t < t_in:
            continue

        if t_out is None:
            # Open-ended zoom
            if t < ramp_in_end:
                p = (t - t_in) / ramp_sec if ramp_sec > 0 else 1.0
                current_zoom = 1.0 + (zoom_factor - 1.0) * smoothstep(p)
            else:
                current_zoom = zoom_factor
            active_px, active_py = px, py
            break
        else:
            ramp_out_end = t_out + ramp_sec
            if t < ramp_in_end:
                p = (t - t_in) / ramp_sec if ramp_sec > 0 else 1.0
                current_zoom = 1.0 + (zoom_factor - 1.0) * smoothstep(p)
                active_px, active_py = px, py
                break
            elif t < t_out:
                current_zoom = zoom_factor
                active_px, active_py = px, py
                break
            elif t < ramp_out_end:
                p = (t - t_out) / ramp_sec if ramp_sec > 0 else 1.0
                current_zoom = 1.0 + (zoom_factor - 1.0) * (1.0 - smoothstep(p))
                active_px, active_py = px, py
                break
            else:
                # Past this interval
                continue

    return current_zoom, active_px, active_py


def build_zoom_filter(intervals: List[Dict[str, Any]], width: int, height: int, fps: int = 25, zoom_factor: float = 2.0, ramp_sec: float = 0.5) -> str:
    """
    Constructs the FFmpeg zoompan filter expression.
    Uses smoothstep easing, per-interval mouse coordinates, and bounds clamping.
    """
    if not intervals:
        return f"zoompan=z=1.0:x=0:y=0:d=1:s={width}x{height}:fps={fps}"

    # Build zoom expression: z='...'
    # If time in ramp-in -> smoothstep in
    # If time in hold -> zoom_factor
    # If time in ramp-out -> smoothstep out
    z_expr = "1.0"
    for item in reversed(intervals):
        t_in = item["t_in"]
        t_out = item["t_out"]
        r = ramp_sec if ramp_sec > 0 else 0.001
        z_max = zoom_factor
        delta_z = z_max - 1.0

        p_in = f"((time-{t_in:.3f})/{r:.3f})"
        ease_in = f"(3*pow({p_in},2)-2*pow({p_in},3))"
        z_ramp_in = f"(1.0+{delta_z:.3f}*{ease_in})"

        if t_out is None:
            # Open-ended zoom: ramp in then hold forever
            cond_in = f"between(time,{t_in:.3f},{t_in+r:.3f})"
            cond_hold = f"gte(time,{t_in+r:.3f})"
            z_expr = f"if({cond_in},{z_ramp_in},if({cond_hold},{z_max:.3f},{z_expr}))"
        else:
            p_out = f"((time-{t_out:.3f})/{r:.3f})"
            ease_out = f"(1.0-(3*pow({p_out},2)-2*pow({p_out},3)))"
            z_ramp_out = f"(1.0+{delta_z:.3f}*{ease_out})"

            cond_in = f"between(time,{t_in:.3f},{t_in+r:.3f})"
            cond_hold = f"between(time,{t_in+r:.3f},{t_out:.3f})"
            cond_out = f"between(time,{t_out:.3f},{t_out+r:.3f})"

            z_expr = f"if({cond_in},{z_ramp_in},if({cond_hold},{z_max:.3f},if({cond_out},{z_ramp_out},{z_expr})))"

    # Build dynamic target mouse coordinates (PX and PY)
    px_expr = f"{width / 2.0:.1f}"
    py_expr = f"{height / 2.0:.1f}"

    for item in reversed(intervals):
        t_in = item["t_in"]
        t_out = item["t_out"]
        t_end = (t_out + ramp_sec) if t_out is not None else 999999.0
        cond = f"between(time,{t_in:.3f},{t_end:.3f})"
        px_expr = f"if({cond},{item['x']:.1f},{px_expr})"
        py_expr = f"if({cond},{item['y']:.1f},{py_expr})"

    x_expr = f"clip({px_expr}-iw/(2*zoom),0,iw-iw/zoom)"
    y_expr = f"clip({py_expr}-ih/(2*zoom),0,ih-ih/zoom)"

    vf = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps}"
    return vf


def build_ffmpeg_command(
    video_path: str,
    sidecar_data: Dict[str, Any],
    output_path: str,
    ffmpeg_bin: str = "ffmpeg",
) -> List[str]:
    """
    Builds the full FFmpeg command list.
    If no events are present, selects the 'copy unchanged' path.
    """
    events = sidecar_data.get("events", [])
    intervals = pair_zoom_events(events)

    if not intervals:
        # No events -> copy unchanged path
        return [
            ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-c", "copy",
            output_path,
        ]

    viewport = sidecar_data.get("viewport", {"width": 1280, "height": 720})
    w = int(viewport.get("width", 1280))
    h = int(viewport.get("height", 720))
    fps = int(sidecar_data.get("fps", 25))
    zoom_factor = float(sidecar_data.get("zoom_factor", 2.0))
    ramp_sec = float(sidecar_data.get("ramp_sec", 0.5))

    vf = build_zoom_filter(intervals, width=w, height=h, fps=fps, zoom_factor=zoom_factor, ramp_sec=ramp_sec)

    return [
        ffmpeg_bin,
        "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libvpx-vp9",
        output_path,
    ]


def apply_zoom(
    video_path: str,
    sidecar_path: Optional[str] = None,
    output_path: Optional[str] = None,
    dry_run: bool = False,
    ffmpeg_bin: Optional[str] = None,
    zoom_factor: Optional[float] = None,
    ramp_sec: Optional[float] = None,
    fps: Optional[int] = None,
) -> Tuple[int, str]:
    """
    Main runner for zoom post-processing.
    Returns (exit_code, command_or_output_path).
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Input video not found: {video_path}")

    actual_ffmpeg = find_ffmpeg(ffmpeg_bin)
    resolved_sidecar = find_sidecar(video_path, sidecar_path)

    sidecar_data = parse_sidecar(resolved_sidecar)
    if zoom_factor is not None:
        sidecar_data["zoom_factor"] = zoom_factor
    if ramp_sec is not None:
        sidecar_data["ramp_sec"] = ramp_sec
    if fps is not None:
        sidecar_data["fps"] = fps

    if not output_path:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}.zoomed{ext or '.webm'}"

    cmd = build_ffmpeg_command(
        video_path=video_path,
        sidecar_data=sidecar_data,
        output_path=output_path,
        ffmpeg_bin=actual_ffmpeg,
    )

    cmd_string = subprocess.list2cmdline(cmd)

    if dry_run:
        print("[DRY RUN] FFmpeg command:")
        print(cmd_string)
        return 0, cmd_string

    print(f"Applying zoom to '{video_path}' -> '{output_path}'...")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        print(f"FFmpeg error (code {res.returncode}):\n{res.stderr}", file=sys.stderr)
        return res.returncode, res.stderr

    print(f"Success! Zoomed video generated at: {output_path}")
    return 0, output_path


def main():
    parser = argparse.ArgumentParser(description="Camtasia-style zoom effect post-processor using FFmpeg zoompan")
    parser.add_argument("--video", required=True, help="Path to input video file (e.g. video/ACME_GmbH.webm)")
    parser.add_argument("--sidecar", default=None, help="Path to sidecar .zoom.json file (default: auto-detected)")
    parser.add_argument("--output", default=None, help="Path to output .webm file (default: <video>.zoomed.webm)")
    parser.add_argument("--dry-run", action="store_true", help="Print FFmpeg command without encoding")
    parser.add_argument("--ffmpeg", default=None, help="Custom path to ffmpeg binary")
    parser.add_argument("--zoom-factor", type=float, default=None, help="Override zoom factor (default from sidecar or 2.0)")
    parser.add_argument("--ramp-sec", type=float, default=None, help="Override ramp duration in seconds (default from sidecar or 0.5)")
    parser.add_argument("--fps", type=int, default=None, help="Override video FPS (default from sidecar or 25)")

    args = parser.parse_args()

    try:
        code, msg = apply_zoom(
            video_path=args.video,
            sidecar_path=args.sidecar,
            output_path=args.output,
            dry_run=args.dry_run,
            ffmpeg_bin=args.ffmpeg,
            zoom_factor=args.zoom_factor,
            ramp_sec=args.ramp_sec,
            fps=args.fps,
        )
        sys.exit(code)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
