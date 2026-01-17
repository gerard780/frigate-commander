#!/usr/bin/env python3
"""
frigate_sources.py

Responsible for ONE thing:
- Given segments JSON, decide per segment:
    - DISK source (preferred) using Frigate recordings folder, or
    - VOD source fallback (HLS /vod/.../master.m3u8)
- Emit a manifest JSON that render step can consume.

Supports your disk naming:
  recordings/YYYY-MM-DD/HH/<camera>/MM.SS.mp4
(and also epoch.mp4 if you ever have it)
"""

import os
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from statistics import median
from typing import List, Tuple, Optional, Dict, Any

import requests

from utils import vod_url as _vod_url


@dataclass
class Config:
    vod_url_template: str = "{base}/vod/{camera}/start/{start}/end/{end}/master.m3u8"
    default_recordings_path: str = "/home/gdupont/docker/frigate/storage/recordings"
    headers: dict = None  # optional auth headers

CFG = Config()


def vod_url(base_url: str, camera: str, start: int, end: int) -> str:
    """Generate a VOD URL using CFG.vod_url_template."""
    return _vod_url(base_url, camera, start, end, template=CFG.vod_url_template)


def expand_path(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def probe_url(url: str) -> bool:
    headers = CFG.headers or {}
    try:
        r = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def iter_utc_hours(start_utc: datetime, end_utc: datetime) -> List[Tuple[str, str]]:
    hours = []
    cur = start_utc.replace(minute=0, second=0, microsecond=0)
    while cur < end_utc:
        hours.append((cur.strftime("%Y-%m-%d"), cur.strftime("%H")))
        cur += timedelta(hours=1)
    return hours


def parse_filename_ts(base_name_no_ext: str, day_str: str, hour_str: str, tz: ZoneInfo) -> Optional[int]:
    # epoch.mp4
    if base_name_no_ext.isdigit():
        try:
            return int(base_name_no_ext)
        except Exception:
            return None

    # MM.SS.mp4 in hour folder
    parts = base_name_no_ext.split(".")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        mm = int(parts[0]); ss = int(parts[1])
        if 0 <= mm <= 59 and 0 <= ss <= 59:
            y, m, d = map(int, day_str.split("-"))
            hh = int(hour_str)
            dt = datetime(y, m, d, hh, mm, ss, tzinfo=tz)
            return int(dt.timestamp())

    return None


def scan_index(recordings_root: str, camera: str, start_utc: datetime, end_utc: datetime, after_ts: int, before_ts: int, tz: ZoneInfo):
    """
    Build sorted list of (chunk_start_ts, file_path) for chunks likely overlapping the window.
    """
    recordings_root = expand_path(recordings_root)
    if not os.path.isdir(recordings_root):
        return [], None, f"recordings path not found: {recordings_root}"

    entries: List[Tuple[int, str]] = []
    for day_str, hour_str in iter_utc_hours(start_utc, end_utc):
        cam_dir = os.path.join(recordings_root, day_str, hour_str, camera)
        if not os.path.isdir(cam_dir):
            continue
        try:
            for name in os.listdir(cam_dir):
                if not name.endswith(".mp4"):
                    continue
                ts = parse_filename_ts(name[:-4], day_str, hour_str, tz)
                if ts is None:
                    continue
                if ts < after_ts - 3600 or ts > before_ts + 3600:
                    continue
                entries.append((ts, os.path.join(cam_dir, name)))
        except FileNotFoundError:
            continue

    if not entries:
        return [], None, "no recordings found in scanned folders"

    entries.sort(key=lambda x: x[0])

    diffs = []
    last = None
    for ts, _ in entries:
        if last is not None:
            d = ts - last
            if 0 < d <= 60:
                diffs.append(d)
        last = ts

    cadence = int(round(median(diffs))) if diffs else None
    return entries, cadence, None


def find_files_for_segment(index: List[Tuple[int, str]], cadence: Optional[int], seg_start: int, seg_end: int,
                           start_slop_mult: float, end_slop_mult: float):
    """
    Choose a minimal set of files that likely cover [seg_start, seg_end).

    Heuristic:
      - pick last chunk with ts <= seg_start
      - include subsequent chunks while ts < seg_end
      - if cadence known, tolerate some slop near edges
    """
    if not index:
        return None, "empty index"

    lo, hi = 0, len(index) - 1
    pos = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if index[mid][0] <= seg_start:
            pos = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if pos < 0:
        return None, "no chunk starts before segment start"

    selected: List[Tuple[int, str]] = []
    i = pos
    while i < len(index) and index[i][0] < seg_end:
        selected.append(index[i])
        i += 1
    if not selected:
        selected = [index[pos]]

    first_ts = selected[0][0]
    last_ts = selected[-1][0]

    if cadence is not None:
        start_tol = int(round(start_slop_mult * cadence))
        end_tol = int(round(end_slop_mult * cadence))
        if seg_start > first_ts + start_tol:
            return None, f"gap before start (seg_start {seg_start} >> {first_ts}, cadence~{cadence}s)"
        if seg_end > last_ts + end_tol:
            return None, f"end beyond chunks (seg_end {seg_end} >> {last_ts}, cadence~{cadence}s)"

    return selected, None


def parse_args():
    p = argparse.ArgumentParser(description="Resolve segments to disk files or VOD URLs.")
    p.add_argument("--segments-json", required=True, help="Path to JSON output from frigate_segments.py")
    p.add_argument("--recordings-path", default=CFG.default_recordings_path)
    p.add_argument("--no-disk", action="store_true", default=False)
    p.add_argument("--source", choices=["disk", "vod"], default="disk",
                   help="Choose a single source (no fallback). Default: disk.")

    # how tolerant should disk coverage be?
    p.add_argument("--start-slop", type=float, default=2.0,
                   help="Allow seg_start to be up to start_slop*cadence after chosen first chunk (default 2.0).")
    p.add_argument("--end-slop", type=float, default=4.0,
                   help="Allow seg_end to be up to end_slop*cadence after chosen last chunk (default 4.0).")

    p.add_argument("--probe-vod", action="store_true", default=False,
                   help="Probe first VOD URL (helps catch base-url/proxy issues early).")

    return p.parse_args()


def main():
    import json
    args = parse_args()

    with open(args.segments_json, "r", encoding="utf-8") as f:
        segdoc = json.load(f)

    base_url = segdoc["base_url"]
    camera = segdoc["camera"]
    tz_name = segdoc["timezone"]
    tz = ZoneInfo(tz_name)
    utc = ZoneInfo("UTC")

    after = int(segdoc["window"]["after"])
    before = int(segdoc["window"]["before"])
    # Recordings folder structure is UTC-based; derive scan window from epoch seconds.
    start_utc = datetime.fromtimestamp(after, tz=utc)
    end_utc = datetime.fromtimestamp(before, tz=utc)

    segments = [(int(s["start"]), int(s["end"])) for s in segdoc["segments"]]

    if args.no_disk:
        args.source = "vod"

    disk_index = []
    cadence = None
    disk_err = None
    if args.source == "disk":
        disk_index, cadence, disk_err = scan_index(args.recordings_path, camera, start_utc, end_utc, after, before, utc)
        if not disk_index:
            print("Disk-only: no recordings found; falling back to VOD for all segments.")
            args.source = "vod"

    resolved = []
    used_disk = 0
    used_vod = 0
    disk_failures = []

    for (s, e) in segments:
        entry: Dict[str, Any] = {"start": s, "end": e}
        if args.source == "vod":
            used_vod += 1
            u = vod_url(base_url, camera, s, e)
            entry["source"] = {"type": "vod", "url": u, "reason": "source=vod"}
        else:
            if disk_index:
                chosen, reason = find_files_for_segment(disk_index, cadence, s, e, args.start_slop, args.end_slop)
            else:
                chosen, reason = None, (disk_err or "disk disabled")

            if chosen:
                used_disk += 1
                entry["source"] = {"type": "disk", "files": [p for (_, p) in chosen], "cadence": cadence}
            else:
                disk_failures.append((s, e, reason))

        if "source" in entry:
            resolved.append(entry)

    if args.source == "disk" and disk_failures:
        print("Disk-only: skipped unresolved segments (showing first 10).")
        for s, e, reason in disk_failures[:10]:
            start_local = datetime.fromtimestamp(s, tz=utc).astimezone(tz)
            end_local = datetime.fromtimestamp(e, tz=utc).astimezone(tz)
            start_label = start_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            end_label = end_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            vod = vod_url(base_url, camera, s, e)
            print(f"- {start_label} -> {end_label} ({s}-{e}) {reason}")
            print(f"  VOD: {vod}")

    manifest = {
        "camera": camera,
        "base_url": base_url,
        "timezone": tz_name,
        "window_tag": segdoc["window_tag"],
        "base_day": segdoc["base_day"],
        "base_day_end": segdoc.get("base_day_end", segdoc["base_day"]),
        "window": segdoc["window"],
        "segments": resolved,
        "stats": {
            "segments_total": len(segments),
            "segments_skipped": len(disk_failures) if args.source == "disk" else 0,
            "disk_segments": used_disk,
            "vod_segments": used_vod,
            "disk_index_files": len(disk_index),
            "cadence": cadence,
        }
    }

    if args.probe_vod and used_vod:
        first_vod = next((x for x in resolved if x["source"]["type"] == "vod"), None)
        if first_vod:
            ok = probe_url(first_vod["source"]["url"])
            if not ok:
                raise SystemExit("VOD probe failed (first fallback URL did not respond). Check base-url/proxy/camera.")

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
