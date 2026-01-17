#!/usr/bin/env python3
"""
utils.py

Shared utility functions for frigate-commander modules.
"""

import subprocess
import time
from typing import List, Optional

import requests


class ApiError(Exception):
    """Raised when API request fails after retries."""
    pass


def api_get(base_url: str, path: str, params=None, headers=None,
            retries: int = 3, backoff: float = 1.0, timeout: int = 60):
    """
    Make a GET request to a Frigate API endpoint with retry logic.

    Args:
        base_url: Frigate base URL
        path: API path (e.g., /api/events)
        params: Query parameters
        headers: Optional headers
        retries: Number of retry attempts (default 3)
        backoff: Initial backoff delay in seconds (doubles each retry)
        timeout: Request timeout in seconds

    Raises:
        ApiError: After all retries exhausted
    """
    url = base_url.rstrip("/") + path
    last_error = None

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers or {}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < retries:
                delay = backoff * (2 ** attempt)
                print(f"API timeout, retrying in {delay:.1f}s... (attempt {attempt + 1}/{retries})")
                time.sleep(delay)
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < retries:
                delay = backoff * (2 ** attempt)
                print(f"API connection error, retrying in {delay:.1f}s... (attempt {attempt + 1}/{retries})")
                time.sleep(delay)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 429:  # Rate limited
                last_error = e
                if attempt < retries:
                    delay = backoff * (2 ** attempt) * 2  # Longer delay for rate limit
                    print(f"API rate limited (429), retrying in {delay:.1f}s... (attempt {attempt + 1}/{retries})")
                    time.sleep(delay)
            elif status and 500 <= status < 600:  # Server error
                last_error = e
                if attempt < retries:
                    delay = backoff * (2 ** attempt)
                    print(f"API server error ({status}), retrying in {delay:.1f}s... (attempt {attempt + 1}/{retries})")
                    time.sleep(delay)
            else:
                # 4xx errors (except 429) are not retryable
                raise ApiError(f"API request failed: {e}") from e

    raise ApiError(f"API request failed after {retries} retries: {last_error}") from last_error


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
