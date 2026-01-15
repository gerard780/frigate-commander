#!/usr/bin/env python3
"""
frigate_segments.py

Responsible for ONE thing:
- Query Frigate /api/events for a window
- Filter to "animal" labels
- Convert detections -> padded segments
- Merge overlapping/nearby segments
- Emit JSON describing the segments

This tool does NOT:
- read recordings from disk
- talk to /vod
- run ffmpeg
"""

import math
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, date as date_cls
from zoneinfo import ZoneInfo
from typing import List, Tuple, Dict, Any

import requests
from astral import LocationInfo
from astral.sun import dawn, dusk


@dataclass
class Config:
    # Frigate
    base_url: str = "http://127.0.0.1:5000"
    camera: str = "TapoC560WS"
    timezone: str = "America/New_York"
    headers: dict = None  # optional auth headers

    # Shelbyville KY for dawn/dusk
    latitude: float = 38.2120
    longitude: float = -85.2230

    # Labels
    include_labels = {
        "bird",
        "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe",
        "deer", "raccoon", "squirrel", "rabbit", "fox", "coyote",
        "skunk", "opossum", "possum",
        "chipmunk", "groundhog", "bobcat", "mountain_lion", "cougar",
        "turkey"
    }
    exclude_labels = {
        "person", "car", "truck", "bus", "motorcycle", "bicycle",
        "package", "train", "boat", "airplane"
    }

CFG = Config()


def api_get(base_url: str, path: str, params=None, headers=None):
    url = base_url.rstrip("/") + path
    r = requests.get(url, params=params, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def label_is_animal(label: str) -> bool:
    if label in CFG.exclude_labels:
        return False
    return label in CFG.include_labels


def parse_time_arg(value: str, tz: ZoneInfo) -> datetime:
    s = value.strip()
    if s.replace(".", "", 1).lstrip("-").isdigit():
        ts = float(s)
        return datetime.fromtimestamp(ts, tz=ZoneInfo("UTC")).astimezone(tz)

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def compute_window(args, tz: ZoneInfo):
    """
    Returns:
      after_ts, before_ts, start_local_dt, end_local_dt, window_tag, start_day, end_day
    """
    now_local = datetime.now(tz)
    start_time = getattr(args, "start_time", None)
    end_time = getattr(args, "end_time", None)
    if start_time or end_time:
        if not (start_time and end_time):
            raise SystemExit("start-time and end-time must be provided together")
        if args.dawntodusk or args.dusktodawn:
            raise SystemExit("start-time/end-time cannot be used with dawn/dusk windows")
        start_dt_local = parse_time_arg(start_time, tz)
        end_dt_local = parse_time_arg(end_time, tz)
        if end_dt_local <= start_dt_local:
            raise SystemExit("end-time must be after start-time")
        window_tag = "custom"
        start_day = start_dt_local.date()
        end_day = end_dt_local.date()
        return int(start_dt_local.timestamp()), int(end_dt_local.timestamp()), start_dt_local, end_dt_local, window_tag, start_day, end_day
    start_day = date_cls.fromisoformat(args.start_date) if args.start_date else None
    if start_day is None:
        start_day = date_cls.fromisoformat(args.date) if args.date else (now_local - timedelta(days=1)).date()

    if args.end_date:
        end_day = date_cls.fromisoformat(args.end_date)
    elif args.days:
        if int(args.days) < 1:
            raise SystemExit("days must be >= 1")
        end_day = start_day + timedelta(days=int(args.days) - 1)
    else:
        end_day = start_day

    if end_day < start_day:
        raise SystemExit("end-date must be on or after start-date")

    if args.dawntodusk or args.dusktodawn:
        loc = LocationInfo(
            name="Shelbyville",
            region="KY",
            timezone=args.timezone,
            latitude=args.latitude,
            longitude=args.longitude,
        )
        if args.dusktodawn:
            start_dt_local = dusk(loc.observer, date=start_day, tzinfo=tz)
            end_dt_local = dawn(loc.observer, date=end_day + timedelta(days=1), tzinfo=tz)
            window_tag = "dusktodawn"
        else:
            start_dt_local = dawn(loc.observer, date=start_day, tzinfo=tz)
            end_dt_local = dusk(loc.observer, date=end_day, tzinfo=tz)
            window_tag = "dawntodusk"
    else:
        start_dt_local = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
        end_dt_local = datetime(end_day.year, end_day.month, end_day.day, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
        window_tag = "fullday"

    return int(start_dt_local.timestamp()), int(end_dt_local.timestamp()), start_dt_local, end_dt_local, window_tag, start_day, end_day


def build_segments_from_events(events: List[Dict[str, Any]], window_after: int, window_before: int, pre_pad: int, post_pad: int, min_len: int):
    """
    Convert detection events into padded, clamped segments.

    Returns list[(start,end)] in integer seconds.
    """
    segments: List[Tuple[int, int]] = []
    for ev in events:
        st = ev.get("start_time")
        et = ev.get("end_time") or st
        if st is None:
            continue

        s = int(math.floor(float(st))) - int(pre_pad)
        e = int(math.ceil(float(et))) + int(post_pad)

        s = max(s, window_after)
        e = min(e, window_before)

        if e - s >= int(min_len):
            segments.append((s, e))
    return segments


def merge_segments(segments: List[Tuple[int, int]], merge_gap: int):
    """
    Merge overlapping or near-overlapping segments to guarantee non-overlapping output.
    """
    if not segments:
        return []
    segments = sorted(segments, key=lambda x: x[0])
    merged: List[List[int]] = []
    for s, e in segments:
        if not merged:
            merged.append([s, e])
            continue
        ps, pe = merged[-1]
        if s <= pe + int(merge_gap):
            merged[-1][1] = max(pe, e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def parse_args():
    p = argparse.ArgumentParser(description="Compute animal montage segments from Frigate detections.")
    p.add_argument("--base-url", default=CFG.base_url)
    p.add_argument("--camera", default=CFG.camera)
    p.add_argument("--timezone", default=CFG.timezone)

    p.add_argument("--latitude", type=float, default=CFG.latitude)
    p.add_argument("--longitude", type=float, default=CFG.longitude)

    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday local)")
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD (overrides --date for multi-day)")
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD (end day inclusive)")
    p.add_argument("--days", type=int, default=None, help="Number of days starting at start-date/date")
    p.add_argument("--start-time", default=None,
                   help="Start timestamp (ISO-8601 or epoch seconds, local tz if no offset)")
    p.add_argument("--end-time", default=None,
                   help="End timestamp (ISO-8601 or epoch seconds, local tz if no offset)")

    g = p.add_mutually_exclusive_group()
    g.add_argument("--dawntodusk", action="store_true")
    g.add_argument("--dusktodawn", action="store_true")

    p.add_argument("--pre-pad", type=int, default=5)
    p.add_argument("--post-pad", type=int, default=5)
    p.add_argument("--merge-gap", type=int, default=15)
    p.add_argument("--min-segment-len", type=int, default=2)
    p.add_argument("--min-score", type=float, default=0.0)

    p.add_argument("--limit", type=int, default=5000)
    p.add_argument("--json", action="store_true", help="Output JSON only (no pretty prints)")

    return p.parse_args()


def main():
    args = parse_args()
    tz = ZoneInfo(args.timezone)

    after, before, start_local, end_local, window_tag, start_day, end_day = compute_window(args, tz)

    params = {"camera": args.camera, "after": after, "before": before, "limit": args.limit}
    events = api_get(args.base_url, "/api/events", params=params, headers=CFG.headers)
    if not isinstance(events, list):
        raise SystemExit(f"Unexpected /api/events response: {type(events)}")

    # Filter to animals
    filtered = []
    seen_labels: Dict[str, int] = {}
    for ev in events:
        label = ev.get("label")
        if label:
            seen_labels[label] = seen_labels.get(label, 0) + 1

        if not label or not isinstance(label, str):
            continue

        score = float(ev.get("top_score") or ev.get("score") or 0.0)
        if score < float(args.min_score):
            continue

        if label_is_animal(label):
            filtered.append(ev)

    filtered.sort(key=lambda e: float(e.get("start_time") or 0.0))

    raw_segments = build_segments_from_events(filtered, after, before, args.pre_pad, args.post_pad, args.min_segment_len)
    merged = merge_segments(raw_segments, args.merge_gap)

    out = {
        "camera": args.camera,
        "base_url": args.base_url.rstrip("/"),
        "timezone": args.timezone,
        "window_tag": window_tag,
        "base_day": start_day.isoformat(),
        "base_day_end": end_day.isoformat(),
        "window": {
            "after": after,
            "before": before,
            "start_local": start_local.isoformat(),
            "end_local": end_local.isoformat(),
        },
        "params": {
            "pre_pad": args.pre_pad,
            "post_pad": args.post_pad,
            "merge_gap": args.merge_gap,
            "min_segment_len": args.min_segment_len,
            "min_score": args.min_score,
        },
        "stats": {
            "events_total": len(events),
            "animals_matched": len(filtered),
            "raw_segments": len(raw_segments),
            "merged_segments": len(merged),
            "labels_seen": dict(sorted(seen_labels.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
        "segments": [{"start": s, "end": e} for (s, e) in merged],
    }

    import json
    if args.json:
        print(json.dumps(out))
    else:
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
