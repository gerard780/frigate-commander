#!/usr/bin/env python3
"""
frigate_timelapse.py

Generate a multi-day timelapse from Frigate disk recordings.
This script does NOT use detections; it scans recordings by time window.
"""

import os
import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from datetime import timedelta
from astral import LocationInfo
from astral.sun import dawn, dusk

import frigate_segments
import frigate_sources
import frigate_render
import atexit
import shutil
import sys
import tempfile
from utils import atempo_chain_for_speed, format_duration, run_ffmpeg_with_progress


def _restore_terminal():
    """Restore terminal settings on exit (fixes ffmpeg/subprocess issues)."""
    if sys.stdin.isatty():
        try:
            subprocess.run(["stty", "sane"], stdin=sys.stdin, check=False)
        except Exception:
            pass


atexit.register(_restore_terminal)


@dataclass
class Config:
    out_dir: str = "./montages"
    default_timelapse: float = 50.0
    default_fps: int = 20
    default_encoder: str = "hevc_nvenc"
    default_nvenc_cq: int = 19
    default_x265_crf: int = 18

CFG = Config()


def build_concat_entries(files: List[str]) -> List[str]:
    return [f"file '{p}'\n" for p in files]


def compute_sun_windows(start_day, end_day, mode: str, latitude: float, longitude: float, tz,
                        dawn_offset: int = 0, dusk_offset: int = 0) -> List[tuple]:
    """
    Compute dawn/dusk windows for each day in range.

    Args:
        start_day: Start date
        end_day: End date (inclusive)
        mode: 'dawntodusk' or 'dusktodawn'
        latitude, longitude: Location for sun calculations
        tz: Timezone
        dawn_offset: Minutes to add to dawn time (positive = later)
        dusk_offset: Minutes to add to dusk time (positive = later)

    Returns:
        List of (start_ts, end_ts) tuples for valid time windows
    """
    from datetime import date as date_cls

    loc = LocationInfo(
        name="Location",
        region="",
        timezone=str(tz),
        latitude=latitude,
        longitude=longitude,
    )

    windows = []
    current = start_day

    while current <= end_day:
        try:
            if mode == 'dawntodusk':
                # Daytime: dawn to dusk on same day
                start_dt = dawn(loc.observer, date=current, tzinfo=tz) + timedelta(minutes=dawn_offset)
                end_dt = dusk(loc.observer, date=current, tzinfo=tz) + timedelta(minutes=dusk_offset)
            else:
                # Nighttime: dusk today to dawn tomorrow
                start_dt = dusk(loc.observer, date=current, tzinfo=tz) + timedelta(minutes=dusk_offset)
                end_dt = dawn(loc.observer, date=current + timedelta(days=1), tzinfo=tz) + timedelta(minutes=dawn_offset)

            windows.append((int(start_dt.timestamp()), int(end_dt.timestamp())))
        except Exception:
            pass  # Skip days with calculation errors (polar regions)

        current += timedelta(days=1)

    return windows


def is_in_sun_windows(ts: int, windows: List[tuple]) -> bool:
    """Check if a timestamp falls within any of the sun windows."""
    for start_ts, end_ts in windows:
        if start_ts <= ts < end_ts:
            return True
    return False


def generate_vod_segments(base_url: str, camera: str, after: int, before: int,
                          sample_interval: float, sun_windows: Optional[List[tuple]] = None) -> List[tuple]:
    """
    Generate VOD URL segments for timelapse.

    Returns list of (timestamp, vod_url) tuples, similar to disk_index format.
    Each segment covers sample_interval seconds.
    """
    segments = []
    current_ts = after

    while current_ts < before:
        # Check sun window filter if provided
        if sun_windows is None or is_in_sun_windows(current_ts, sun_windows):
            # Generate VOD URL for this chunk
            chunk_end = min(current_ts + int(sample_interval), before)
            url = frigate_sources.vod_url(base_url, camera, current_ts, chunk_end)
            segments.append((current_ts, url))

        current_ts += int(sample_interval)

    return segments


def _parse_cache_path_from_recording(file_path: str, cache_dir: str) -> Optional[str]:
    """
    Parse recording path to generate a timestamp-based cache path.
    Frigate recordings: .../YYYY-MM-DD/HH/camera/MM.SS.mp4
    Cache structure: cache_dir/camera/YYYY-MM-DD/HH-MM-SS.webp
    """
    import re
    # Match Frigate recording path pattern
    match = re.search(r'/(\d{4}-\d{2}-\d{2})/(\d{2})/([^/]+)/(\d{2})\.(\d{2})\.mp4$', file_path)
    if match:
        date, hour, camera, minute, second = match.groups()
        return os.path.join(cache_dir, camera, date, f"{hour}-{minute}-{second}.webp")
    # Fallback to hash-based for non-standard paths
    import hashlib
    cache_key = hashlib.md5(file_path.encode()).hexdigest()
    return os.path.join(cache_dir, "_other", f"{cache_key}.webp")


def _extract_one_frame(args):
    """Worker function for parallel frame extraction."""
    idx, path, out_dir, cache_dir = args
    out_path = os.path.join(out_dir, f"{idx:08d}.webp")

    # Check cache first
    cache_path = None
    if cache_dir:
        cache_path = _parse_cache_path_from_recording(path, cache_dir)
        if cache_path and os.path.exists(cache_path):
            # Copy from cache
            try:
                shutil.copy2(cache_path, out_path)
                return (True, "cached")
            except Exception:
                pass  # Fall through to extraction

    # Extract frame as WebP (~30% smaller than JPEG at similar quality)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", path, "-frames:v", "1", "-quality", "85", out_path]
    try:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and os.path.exists(out_path):
            # Save to cache if enabled
            if cache_dir and cache_path:
                try:
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    shutil.copy2(out_path, cache_path)
                except Exception:
                    pass  # Cache write failure is non-fatal
            return (True, "extracted")
        return (False, "failed")
    except Exception:
        return (False, "error")


def extract_first_frames(files: List[str], out_dir: str, cache_dir: Optional[str] = None) -> int:
    """
    Extract the first frame from each file to an image sequence.
    Uses parallel processing for speed.
    If cache_dir is provided, reuses previously extracted frames.
    Returns the number of successfully extracted frames.
    """
    import signal
    import time
    from concurrent.futures import ProcessPoolExecutor, as_completed

    os.makedirs(out_dir, exist_ok=True)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    total = len(files)

    # Prepare work items
    work = [(idx, path, out_dir, cache_dir) for idx, path in enumerate(files)]

    # Use process pool - more workers = faster, but don't overwhelm I/O
    max_workers = min(16, (os.cpu_count() or 4) * 2)
    cache_status = f", cache={cache_dir}" if cache_dir else ""
    print(f"Extracting first frame from {total} files (workers={max_workers}{cache_status})...")

    success = 0
    cached = 0
    done = 0
    succeeded_indices = []
    start_time = time.monotonic()
    interrupt_count = [0]  # Use list to avoid issues with nested scope
    # Rolling window for accurate ETA (track last N timestamps)
    window_size = 500
    window_times = []  # (done_count, timestamp) pairs

    def handle_interrupt(signum, frame):
        interrupt_count[0] += 1
        if interrupt_count[0] == 1:
            print("\n  Stopping after current tasks... (Ctrl+C again to force quit)")
        elif interrupt_count[0] == 2:
            print("\n  Force quitting...")
        # Ignore additional Ctrl+C presses

    # Set up interrupt handler
    original_handler = signal.signal(signal.SIGINT, handle_interrupt)

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_extract_one_frame, w): w[0] for w in work}
            for future in as_completed(futures):
                if interrupt_count[0] >= 2:
                    # Force stop - cancel everything immediately
                    for f in futures:
                        f.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                done += 1
                idx = futures[future]
                try:
                    ok, status = future.result(timeout=0.1)
                    if ok:
                        success += 1
                        succeeded_indices.append(idx)
                        if status == "cached":
                            cached += 1
                except Exception:
                    pass

                # Stop after current batch if gracefully interrupted
                if interrupt_count[0] == 1:
                    # Cancel pending futures
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break

                if done % 500 == 0 or done == total:
                    now = time.monotonic()
                    window_times.append((done, now))
                    # Keep only recent entries for rolling window
                    while len(window_times) > 10:
                        window_times.pop(0)

                    # Calculate rate from rolling window
                    if len(window_times) >= 2:
                        oldest_done, oldest_time = window_times[0]
                        newest_done, newest_time = window_times[-1]
                        window_elapsed = newest_time - oldest_time
                        window_count = newest_done - oldest_done
                        rate = window_count / window_elapsed if window_elapsed > 0 else 0
                    else:
                        # Fallback to overall rate for first window
                        elapsed = now - start_time
                        rate = done / elapsed if elapsed > 0 else 0

                    remaining = (total - done) / rate if rate > 0 else 0
                    eta = format_duration(remaining)
                    cache_info = f", cached={cached}" if cache_dir else ""
                    print(f"  Progress: {done}/{total} (success={success}{cache_info}) ETA: {eta}")
    finally:
        # Restore original handler
        signal.signal(signal.SIGINT, original_handler)

    if interrupt_count[0] > 0:
        print(f"  Stopped. Extracted {success} frames.")
        raise SystemExit(1)

    # Renumber files to be sequential (required for ffmpeg image2 demuxer)
    if succeeded_indices:
        succeeded_indices.sort()
        print(f"  Renumbering {len(succeeded_indices)} frames to sequential...")
        for new_idx, old_idx in enumerate(succeeded_indices):
            old_path = os.path.join(out_dir, f"{old_idx:08d}.webp")
            new_path = os.path.join(out_dir, f"frame_{new_idx:08d}.webp")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)

    if cache_dir and cached > 0:
        print(f"  Cache hits: {cached}/{success} frames reused")

    total_time = time.monotonic() - start_time
    print(f"  Completed in {format_duration(total_time)} ({success} frames)")

    return success


def encode_image_sequence(img_dir: str, out_mp4: str, *,
                          fps: int,
                          encoder: str,
                          preset: str,
                          cq: Optional[int],
                          crf: Optional[int],
                          maxrate: Optional[str],
                          bufsize: Optional[str],
                          scale: Optional[str],
                          spatial_aq: bool,
                          temporal_aq: bool,
                          aq_strength: Optional[int]):
    """Encode an image sequence (numbered WebP images) to video."""
    pattern = os.path.join(img_dir, "frame_%08d.webp")

    cmd = ["ffmpeg", "-y", "-hide_banner"]
    cmd += [
        "-framerate", str(fps),
        "-i", pattern,
    ]

    # Video filter for scaling if needed
    vf_parts = []
    if scale:
        vf_parts.append(f"scale={scale}")
    if vf_parts:
        cmd += ["-filter:v", ",".join(vf_parts)]

    # Encoder settings
    if encoder in ("hevc_nvenc", "h264_nvenc"):
        cmd += [
            "-c:v", encoder,
            "-preset", preset,
            "-rc:v", "vbr_hq",
        ]
        if cq is not None:
            cmd += ["-cq:v", str(cq)]
        if spatial_aq:
            cmd += ["-spatial-aq", "1"]
            if aq_strength is not None:
                cmd += ["-aq-strength", str(aq_strength)]
        if temporal_aq:
            cmd += ["-temporal-aq", "1"]
        cmd += ["-b:v", "0"]
        if maxrate:
            cmd += ["-maxrate:v", str(maxrate)]
        if bufsize:
            cmd += ["-bufsize:v", str(bufsize)]
    elif encoder in ("libx265", "libx264"):
        cmd += [
            "-c:v", encoder,
            "-preset", preset,
        ]
        if crf is not None:
            cmd += ["-crf", str(crf)]
    else:
        cmd += ["-c:v", encoder]

    cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", out_mp4]

    print(f"Encoding {out_mp4}...")
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit("ffmpeg encoding failed")


def parse_bitrate(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("k"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 1000 * 1000)
    if text.endswith("g"):
        return int(float(text[:-1]) * 1000 * 1000 * 1000)
    return int(float(text))


def format_bytes(num_bytes: int) -> str:
    if num_bytes < 1000 * 1000:
        return f"{num_bytes / 1000:.1f} KB"
    if num_bytes < 1000 * 1000 * 1000:
        return f"{num_bytes / (1000 * 1000):.2f} MB"
    return f"{num_bytes / (1000 * 1000 * 1000):.2f} GB"


def probe_video_info(path: str) -> Optional[dict]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate",
        "-of", "json",
        path,
    ]
    try:
        out = subprocess.check_output(cmd).decode("utf-8", errors="replace")
    except Exception:
        return None
    import json
    data = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        return None
    return streams[0]


def parse_fraction(text: str) -> Optional[float]:
    if not text or text == "0/0":
        return None
    if "/" in text:
        num, den = text.split("/", 1)
        try:
            return float(num) / float(den)
        except Exception:
            return None
    try:
        return float(text)
    except Exception:
        return None


def estimate_bitrate_bps(width: int, height: int, fps: float, encoder: str,
                         cq: Optional[int], crf: Optional[int]) -> Optional[int]:
    if width <= 0 or height <= 0 or fps <= 0:
        return None

    is_hevc = encoder in ("hevc_nvenc", "hevc_qsv", "libx265")
    base_bpp = 0.05 if is_hevc else 0.08

    q = cq if cq is not None else crf
    if q is None:
        quality_factor = 1.0
    else:
        quality_factor = (32.0 - float(q)) / 12.0
        quality_factor = max(0.6, min(1.8, quality_factor))

    bpp = base_bpp * quality_factor
    return int(round(width * height * fps * bpp))


def build_ffmpeg_cmd(concat_path: str, out_mp4: str, *,
                     timelapse: float,
                     frame_sample: Optional[float],
                     sample_interval: Optional[float],
                     fps: int,
                     encoder: str,
                     preset: str,
                     cq: Optional[int],
                     crf: Optional[int],
                     maxrate: Optional[str],
                     bufsize: Optional[str],
                     keep_audio: bool,
                     scale: Optional[str],
                     use_cuda: bool,
                     spatial_aq: bool,
                     temporal_aq: bool,
                     aq_strength: Optional[int],
                     qsv_device: Optional[str],
                     vaapi_device: Optional[str]):
    def build_video_filter(use_hw_upload: bool, use_cuda_scale: bool) -> str:
        parts = []
        if sample_interval is not None and sample_interval > 0:
            # FAST segment-level sampling: files already filtered, just take first frame of each
            # This is much faster as we skip entire files and only decode first frame
            parts.append("select='eq(n\\,0)'")
            parts.append(f"setpts=N/{fps}/TB")
        elif frame_sample is not None and frame_sample > 0:
            # Frame sampling: select 1 frame per N seconds of source footage
            # Using select filter (faster than fps filter - can skip decode on some codecs)
            # then setpts to fix timestamps for smooth playback at target fps
            parts.append(f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{frame_sample})'")
            parts.append(f"setpts=N/{fps}/TB")
        else:
            # Traditional timelapse: keep all frames, compress timestamps
            parts.append(f"setpts=PTS/{timelapse}")
        if scale:
            if use_cuda_scale:
                parts.append(f"scale_npp={scale}")
            else:
                parts.append(f"scale={scale}")
        if use_hw_upload:
            parts.append("format=nv12")
            parts.append("hwupload")
        return ",".join(parts)

    cmd = ["ffmpeg", "-y"]
    if use_cuda and encoder in ("hevc_nvenc", "h264_nvenc"):
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    cmd += [
        "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-r", str(fps),
    ]

    if encoder in ("hevc_nvenc", "h264_nvenc"):
        cmd += ["-filter:v", build_video_filter(False, use_cuda and bool(scale))]
        cmd += [
            "-c:v", encoder,
            "-preset", preset,
            "-rc:v", "vbr_hq",
        ]
        if cq is not None:
            cmd += ["-cq:v", str(cq)]
        if spatial_aq:
            cmd += ["-spatial-aq", "1"]
            if aq_strength is not None:
                cmd += ["-aq-strength", str(aq_strength)]
        if temporal_aq:
            cmd += ["-temporal-aq", "1"]
        cmd += ["-b:v", "0"]
        if maxrate:
            cmd += ["-maxrate:v", str(maxrate)]
        if bufsize:
            cmd += ["-bufsize:v", str(bufsize)]
    elif encoder in ("hevc_qsv", "h264_qsv"):
        if qsv_device:
            cmd += ["-init_hw_device", f"qsv=hw:{qsv_device}"]
        else:
            cmd += ["-init_hw_device", "qsv=hw"]
        cmd += ["-filter_hw_device", "hw"]
        cmd += ["-filter:v", build_video_filter(True, False)]
        cmd += [
            "-c:v", encoder,
            "-preset", preset,
        ]
        if cq is not None:
            cmd += ["-global_quality", str(cq)]
        if maxrate:
            cmd += ["-maxrate", str(maxrate)]
        if bufsize:
            cmd += ["-bufsize", str(bufsize)]
    elif encoder in ("hevc_vaapi", "h264_vaapi"):
        device = vaapi_device or "/dev/dri/renderD128"
        cmd += ["-vaapi_device", device]
        cmd += ["-filter:v", build_video_filter(True, False)]
        cmd += [
            "-c:v", encoder,
        ]
        if cq is not None:
            cmd += ["-qp", str(cq)]
        if maxrate:
            cmd += ["-maxrate", str(maxrate)]
        if bufsize:
            cmd += ["-bufsize", str(bufsize)]
    elif encoder in ("libx265", "libx264"):
        cmd += ["-filter:v", build_video_filter(False, False)]
        cmd += [
            "-c:v", encoder,
            "-preset", preset,
        ]
        if crf is not None:
            cmd += ["-crf", str(crf)]
    else:
        raise SystemExit(f"Unsupported encoder: {encoder}")

    if encoder in ("hevc_qsv", "h264_qsv", "hevc_vaapi", "h264_vaapi"):
        cmd += ["-pix_fmt", "nv12"]
    elif not (use_cuda and encoder in ("hevc_nvenc", "h264_nvenc")):
        cmd += ["-pix_fmt", "yuv420p"]

    if keep_audio:
        factors = atempo_chain_for_speed(float(timelapse))
        atempo = ",".join([f"atempo={f:.6f}".rstrip("0").rstrip(".") for f in factors])
        cmd += ["-filter:a", atempo]
    else:
        cmd += ["-an"]

    cmd += ["-movflags", "+faststart", out_mp4]
    return cmd


def parse_args():
    p = argparse.ArgumentParser(description="Multi-day timelapse from Frigate recordings (disk or VOD).")
    p.add_argument("--camera", required=True)
    p.add_argument("--base-url", default=frigate_segments.CFG.base_url,
                   help="Frigate base URL (required for VOD source)")
    p.add_argument("--source", choices=["disk", "vod"], default="disk",
                   help="Recording source: disk (local files) or vod (stream from Frigate)")
    p.add_argument("--recordings-path", default=frigate_sources.CFG.default_recordings_path)
    p.add_argument("--recordings-path-fallback", action="append", default=[],
                   help="Additional recordings paths to check (can be specified multiple times). "
                        "Useful for multiple Frigate instances with NFS shares.")
    p.add_argument("--timezone", default=frigate_segments.CFG.timezone)

    # window selection
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday local)")
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD (overrides --date)")
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--days", type=int, default=None, help="Number of days starting at start-date/date")
    p.add_argument("--start-time", default=None,
                   help="Start timestamp (ISO-8601 or epoch seconds, local tz if no offset)")
    p.add_argument("--end-time", default=None,
                   help="End timestamp (ISO-8601 or epoch seconds, local tz if no offset)")

    g = p.add_mutually_exclusive_group()
    g.add_argument("--dawntodusk", action="store_true")
    g.add_argument("--dusktodawn", action="store_true")

    # location for dawn/dusk
    p.add_argument("--latitude", type=float, default=frigate_segments.CFG.latitude)
    p.add_argument("--longitude", type=float, default=frigate_segments.CFG.longitude)
    p.add_argument("--dawn-offset", type=int, default=0, metavar="MINUTES",
                   help="Offset for dawn time in minutes. Positive = start later, negative = start earlier.")
    p.add_argument("--dusk-offset", type=int, default=0, metavar="MINUTES",
                   help="Offset for dusk time in minutes. Positive = end later, negative = end earlier. "
                        "E.g., --dusk-offset -30 ends 30 minutes before dusk.")

    # output
    p.add_argument("--out-dir", default=CFG.out_dir)
    p.add_argument("--out-file", default=None)

    # timelapse / encode
    p.add_argument("--timelapse", type=float, default=CFG.default_timelapse,
                   help="Speed multiplier using setpts (keeps all frames, compresses time)")
    p.add_argument("--frame-sample", type=float, default=None, metavar="SECONDS",
                   help="Frame sampling interval in seconds (e.g., 5 = 1 frame per 5 seconds). "
                        "Alternative to --timelapse that samples frames instead of time-stretching.")
    p.add_argument("--sample-interval", type=float, default=None, metavar="SECONDS",
                   help="FAST segment-level sampling: select 1 file per N seconds, take first frame. "
                        "Much faster than --frame-sample for long periods (days/weeks/months). "
                        "E.g., --sample-interval 60 = 1 frame per minute.")
    p.add_argument("--frame-cache", default=None, metavar="DIR",
                   help="Directory to cache extracted frames. Reuses frames from previous runs "
                        "for overlapping time ranges. Default: {out-dir}/frame_cache when using --sample-interval")
    p.add_argument("--no-frame-cache", action="store_true", default=False,
                   help="Disable frame caching (not recommended)")
    p.add_argument("--fps", type=int, default=CFG.default_fps)
    p.add_argument("--encoder", default=CFG.default_encoder,
                   choices=["hevc_nvenc", "h264_nvenc", "hevc_qsv", "h264_qsv", "hevc_vaapi", "h264_vaapi", "libx265", "libx264"])
    p.add_argument("--preset", default=None)
    p.add_argument("--cq", type=int, default=None, help="NVENC constant quality (e.g. 19-25)")
    p.add_argument("--crf", type=int, default=None, help="x264/x265 CRF (e.g. 18-24)")
    p.add_argument("--maxrate", default=None, help="NVENC maxrate, e.g. 12M")
    p.add_argument("--bufsize", default=None, help="NVENC bufsize, e.g. 24M")
    p.add_argument("--scale", default=None,
                   help="Output resolution, e.g. 1920:1080 or -2:1080 to keep aspect ratio")
    p.add_argument("--cuda", action="store_true", default=False,
                   help="Use CUDA decode + scale_npp (NVENC only)")
    p.add_argument("--spatial-aq", action="store_true", default=None,
                   help="Enable NVENC spatial AQ (default: on for NVENC)")
    p.add_argument("--temporal-aq", action="store_true", default=None,
                   help="Enable NVENC temporal AQ (default: on for NVENC)")
    p.add_argument("--aq-strength", type=int, default=None,
                   help="NVENC AQ strength (default: 8 when spatial AQ is on)")
    p.add_argument("--audio", action="store_true", default=False, help="Keep audio (time-scaled)")
    p.add_argument("--qsv-device", default=None, help="QSV device, e.g. /dev/dri/renderD128")
    p.add_argument("--vaapi-device", default=None, help="VAAPI device, e.g. /dev/dri/renderD128")
    p.add_argument("--estimate-bitrate", default=None,
                   help="Estimate output size using a target bitrate, e.g. 8M or 6000k")

    return p.parse_args()


def main():
    args = parse_args()

    if float(args.timelapse) <= 0:
        raise SystemExit("timelapse must be > 0")

    tz = ZoneInfo(args.timezone)
    utc = ZoneInfo("UTC")

    after, before, start_local, end_local, window_tag, start_day, end_day = frigate_segments.compute_window(args, tz)
    start_utc = datetime.fromtimestamp(after, tz=utc)
    end_utc = datetime.fromtimestamp(before, tz=utc)

    # Compute sun windows early (needed for both disk and VOD filtering)
    is_multiday = (end_day != start_day)
    sun_windows = None
    if is_multiday and (args.dawntodusk or args.dusktodawn):
        mode = 'dawntodusk' if args.dawntodusk else 'dusktodawn'
        sun_windows = compute_sun_windows(
            start_day, end_day, mode,
            args.latitude, args.longitude, tz,
            dawn_offset=args.dawn_offset,
            dusk_offset=args.dusk_offset
        )

    # Source selection: disk or VOD
    use_vod = (args.source == "vod")
    cadence = None

    if use_vod:
        # VOD mode: generate URLs for time chunks
        if args.sample_interval is None:
            # Default to 60s chunks for VOD (required for efficient streaming)
            effective_interval = 60.0
            print(f"VOD mode: using default 60s sample interval")
        else:
            effective_interval = args.sample_interval

        files_with_ts = generate_vod_segments(
            args.base_url, args.camera, after, before,
            effective_interval, sun_windows
        )
        if not files_with_ts:
            raise SystemExit("no VOD segments generated")

        cadence = effective_interval
        files = [url for (ts, url) in files_with_ts]
        print(f"VOD source: {len(files)} segments ({effective_interval}s each)")

    else:
        # Disk mode: scan local recordings
        fallback = args.recordings_path_fallback if args.recordings_path_fallback else None
        disk_index, cadence, disk_err = frigate_sources.scan_index(
            args.recordings_path,
            args.camera,
            start_utc,
            end_utc,
            after,
            before,
            utc,
            fallback_paths=fallback,
        )
        if not disk_index:
            raise SystemExit(disk_err or "no recordings found")

        # Filter files within time window
        files_with_ts = [(ts, p) for (ts, p) in disk_index if after <= ts < before]
        if not files_with_ts:
            raise SystemExit("no recordings within requested window")

        # Apply sun window filter for disk mode
        if sun_windows:
            mode = 'dawntodusk' if args.dawntodusk else 'dusktodawn'
            before_count = len(files_with_ts)
            files_with_ts = [(ts, p) for (ts, p) in files_with_ts if is_in_sun_windows(ts, sun_windows)]
            if not files_with_ts:
                raise SystemExit(f"no recordings within {mode} windows")
            print(f"Sun filter ({mode}): {len(files_with_ts)}/{before_count} files in {len(sun_windows)} windows")

        # For segment-level sampling (--sample-interval), select files at intervals
        if args.sample_interval is not None and args.sample_interval > 0:
            interval = args.sample_interval
            # Group files by which interval bucket they fall into (aligned to start time)
            # This ensures larger intervals are always subsets of smaller ones
            # e.g., 20s picks buckets 0,1,2,3,4,5... and 60s picks buckets 0,3,6...
            buckets = {}
            for ts, p in files_with_ts:
                bucket = int((ts - after) // interval)
                if bucket not in buckets:
                    buckets[bucket] = (ts, p)  # Keep first file in each bucket
            # Sort by bucket and extract files
            files = [p for bucket, (ts, p) in sorted(buckets.items())]
            total_files = len(files_with_ts)
            print(f"Segment sampling: {len(files)}/{total_files} files (1 per {args.sample_interval}s)")
        else:
            files = [p for (ts, p) in files_with_ts]

    if not files:
        raise SystemExit("no files after sampling filter")

    os.makedirs(args.out_dir, exist_ok=True)

    # Default frame cache to {out_dir}/frame_cache when using --sample-interval (disk only)
    frame_cache = args.frame_cache
    if args.sample_interval is not None and not args.no_frame_cache and not use_vod:
        if frame_cache is None:
            frame_cache = os.path.join(args.out_dir, "frame_cache")
    # Disable frame cache for VOD (streams can't be cached the same way)
    if use_vod:
        frame_cache = None
    concat_path = frigate_render.write_concat_file(args.out_dir, args.camera, build_concat_entries(files))

    base_label = start_day.isoformat()
    if end_day != start_day:
        base_label = f"{start_day.isoformat()}_to_{end_day.isoformat()}"

    suffix = window_tag
    if args.sample_interval is not None:
        suffix += f"-sample{args.sample_interval}s"
    elif args.frame_sample is not None:
        suffix += f"-framesample{args.frame_sample}s"
    elif args.timelapse is not None:
        suffix += f"-timelapse{args.timelapse}x"

    out_mp4 = args.out_file or os.path.join(args.out_dir, f"{args.camera}-timelapse-{base_label}-{suffix}.mp4")

    if args.preset is None:
        if args.encoder in ("libx265", "libx264"):
            preset = "slow"
        elif args.encoder in ("hevc_qsv", "h264_qsv"):
            preset = "medium"
        else:
            preset = "p5"
    else:
        preset = args.preset

    cq = args.cq if args.cq is not None else (CFG.default_nvenc_cq if args.encoder.endswith("_nvenc") else None)
    crf = args.crf if args.crf is not None else (CFG.default_x265_crf if args.encoder in ("libx265", "libx264") else None)
    if args.encoder.endswith("_nvenc"):
        spatial_aq = True if args.spatial_aq is None else bool(args.spatial_aq)
        temporal_aq = True if args.temporal_aq is None else bool(args.temporal_aq)
        aq_strength = args.aq_strength if args.aq_strength is not None else 8
    else:
        spatial_aq = False
        temporal_aq = False
        aq_strength = None

    cmd = build_ffmpeg_cmd(
        concat_path,
        out_mp4,
        timelapse=float(args.timelapse),
        frame_sample=args.frame_sample,
        sample_interval=args.sample_interval,
        fps=int(args.fps),
        encoder=args.encoder,
        preset=preset,
        cq=cq,
        crf=crf,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
        keep_audio=bool(args.audio),
        scale=args.scale,
        use_cuda=bool(args.cuda),
        spatial_aq=spatial_aq,
        temporal_aq=temporal_aq,
        aq_strength=aq_strength,
        qsv_device=args.qsv_device,
        vaapi_device=args.vaapi_device,
    )

    window_seconds = max(0, before - after)
    if args.sample_interval is not None:
        # Segment-level sampling: 1 frame per file, output = num_files / fps
        output_seconds = len(files) / float(args.fps)
        # Progress based on output (fast mode processes quickly)
        progress_seconds = output_seconds
    elif args.frame_sample is not None:
        # Frame sampling: output duration = (window_seconds / frame_sample_interval) / fps
        output_seconds = (window_seconds / args.frame_sample) / float(args.fps)
        # For progress tracking, use INPUT duration since that's what's being processed
        progress_seconds = window_seconds
    else:
        # Traditional timelapse: output duration = window_seconds / timelapse_factor
        output_seconds = window_seconds / float(args.timelapse)
        progress_seconds = output_seconds
    estimate_bitrate = args.estimate_bitrate or args.maxrate
    estimate_note = None
    bitrate_bps = None
    if estimate_bitrate:
        bitrate_bps = parse_bitrate(estimate_bitrate)
    else:
        info = probe_video_info(files[0])
        if info:
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            bitrate_bps = estimate_bitrate_bps(width, height, float(args.fps), args.encoder, cq, crf)
            if bitrate_bps:
                estimate_note = "auto"

    if bitrate_bps:
        est_bytes = int(round(output_seconds * bitrate_bps / 8.0))
        note = f" ({estimate_note})" if estimate_note else ""
        estimate_line = f"Estimate{note}: {format_duration(output_seconds)} ~{format_bytes(est_bytes)}"
    else:
        estimate_line = f"Estimate: {format_duration(output_seconds)} (size unknown; set --estimate-bitrate)"

    print(f"Camera:  {args.camera}")
    print(f"Source:  {'VOD' if use_vod else 'disk'}")
    print(f"Window:  {start_local.isoformat()} -> {end_local.isoformat()} ({window_tag})")
    source_label = "URLs" if use_vod else "files"
    print(f"Files:   {len(files)} {source_label} cadence≈{cadence}s")
    print(f"Output:  {out_mp4}")
    if args.sample_interval is not None:
        print(f"Codec:   {args.encoder} preset={preset} sample-interval={args.sample_interval}s fps={args.fps}")
    elif args.frame_sample is not None:
        print(f"Codec:   {args.encoder} preset={preset} frame-sample={args.frame_sample}s fps={args.fps}")
    else:
        print(f"Codec:   {args.encoder} preset={preset} timelapse={args.timelapse}x fps={args.fps}")
    if args.scale:
        print(f"Scale:   {args.scale}")
    if args.cuda and args.encoder in ("hevc_nvenc", "h264_nvenc") and args.sample_interval is None:
        print("CUDA:    enabled (decode + scale_npp)")
    if spatial_aq or temporal_aq:
        aq_bits = []
        if spatial_aq:
            aq_bits.append(f"spatial aq={aq_strength}")
        if temporal_aq:
            aq_bits.append("temporal aq")
        print("AQ:      " + ", ".join(aq_bits))
    print(estimate_line)

    # Use two-pass approach for sample_interval or VOD (MUCH faster)
    # VOD always uses this approach since segments are pre-chunked
    if args.sample_interval is not None or use_vod:
        # Create temp directory for frame extraction
        tmp_dir = tempfile.mkdtemp(prefix="timelapse_frames_")
        try:
            # Pass 1: Extract first frame from each file (parallel, fast)
            extracted = extract_first_frames(files, tmp_dir, cache_dir=frame_cache)
            if extracted == 0:
                raise SystemExit("No frames extracted")
            print(f"Extracted {extracted} frames")

            # Pass 2: Encode image sequence to video
            encode_image_sequence(
                tmp_dir, out_mp4,
                fps=int(args.fps),
                encoder=args.encoder,
                preset=preset,
                cq=cq,
                crf=crf,
                maxrate=args.maxrate,
                bufsize=args.bufsize,
                scale=args.scale,
                spatial_aq=spatial_aq,
                temporal_aq=temporal_aq,
                aq_strength=aq_strength,
            )
        finally:
            # Cleanup temp directory
            shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        # Traditional single-pass approach
        print(f"Concat:  {concat_path}")
        run_ffmpeg_with_progress(cmd, progress_seconds)

    print("DONE:", out_mp4)


if __name__ == "__main__":
    main()
