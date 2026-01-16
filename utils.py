#!/usr/bin/env python3
"""
utils.py

Shared utility functions for frigate-commander modules.
"""

import subprocess
import time
from typing import List, Optional

import requests


def api_get(base_url: str, path: str, params=None, headers=None):
    """Make a GET request to a Frigate API endpoint."""
    url = base_url.rstrip("/") + path
    r = requests.get(url, params=params, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def vod_url(base_url: str, camera: str, start: int, end: int,
            template: str = "{base}/vod/{camera}/start/{start}/end/{end}/master.m3u8") -> str:
    """Generate a Frigate VOD URL for a time range."""
    base = base_url.rstrip("/")
    return template.format(base=base, camera=camera, start=start, end=end)


def atempo_chain_for_speed(speed: float) -> List[float]:
    """
    Decompose a speed factor into a chain of atempo factors.
    FFmpeg atempo filter only supports 0.5-2.0 range, so higher speeds
    require chaining multiple filters.
    """
    factors = []
    remaining = speed
    while remaining > 2.0 + 1e-9:
        factors.append(2.0)
        remaining /= 2.0
    if abs(remaining - 1.0) > 1e-9:
        remaining = max(0.5, min(2.0, remaining))
        factors.append(remaining)
    return factors


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def run_ffmpeg_with_progress(cmd: List[str], total_out_seconds: float,
                              progress_interval: float = 10.0):
    """
    Run an FFmpeg command with real-time progress output.

    Args:
        cmd: FFmpeg command as list of arguments (output file should be last)
        total_out_seconds: Expected output duration for percentage calculation
        progress_interval: Seconds between progress updates (default 10)
    """
    cmd = list(cmd)
    cmd.insert(-1, "-progress")
    cmd.insert(-1, "pipe:1")
    cmd.insert(-1, "-nostats")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    last_emit = time.monotonic()
    out_time_ms = None
    speed = None
    tail = []

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            tail.append(line)
            if len(tail) > 200:
                tail.pop(0)
            continue
        key, val = line.split("=", 1)
        if key == "out_time_ms":
            try:
                out_time_ms = int(val)
            except Exception:
                out_time_ms = None
        elif key == "speed":
            speed = val

        now = time.monotonic()
        if now - last_emit >= progress_interval and out_time_ms is not None:
            elapsed = out_time_ms / 1_000_000.0
            pct = None
            if total_out_seconds > 0:
                pct = min(100.0, max(0.0, 100.0 * elapsed / total_out_seconds))
            pct_text = f"{pct:5.1f}%" if pct is not None else "  n/a"
            speed_text = speed or "?"
            print(f"Progress: {pct_text} time={format_duration(elapsed)} speed={speed_text}")
            last_emit = now

    rc = proc.wait()
    if rc != 0:
        if tail:
            print("ffmpeg output (tail):")
            for line in tail:
                print(line)
        raise SystemExit("ffmpeg failed (see output above).")
