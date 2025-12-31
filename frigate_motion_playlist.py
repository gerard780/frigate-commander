#!/usr/bin/env python3
"""
frigate_motion_playlist.py

Generate an M3U playlist for motion-only review items (no detection event).
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

import requests


@dataclass
class Config:
    base_url: str = "http://127.0.0.1:5000"
    timezone: str = "America/New_York"
    vod_url_template: str = "{base}/vod/{camera}/start/{start}/end/{end}/master.m3u8"

CFG = Config()


def api_get(base_url: str, path: str, params=None, headers=None):
    url = base_url.rstrip("/") + path
    r = requests.get(url, params=params, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def vod_url(base_url: str, camera: str, start: int, end: int) -> str:
    base = base_url.rstrip("/")
    return CFG.vod_url_template.format(base=base, camera=camera, start=start, end=end)


def parse_args():
    p = argparse.ArgumentParser(description="Generate VLC playlist for motion-only review items.")
    p.add_argument("--base-url", default=CFG.base_url)
    p.add_argument("--camera", required=True)
    p.add_argument("--timezone", default=CFG.timezone)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--start", type=float, default=None, help="Epoch seconds (filter start_time >=)")
    p.add_argument("--end", type=float, default=None, help="Epoch seconds (filter start_time <=)")
    p.add_argument("--default-duration", type=int, default=30,
                   help="Seconds to use when end_time is missing (default 30).")
    p.add_argument("--out", required=True, help="Output M3U path.")
    return p.parse_args()


def review_items(base_url: str, camera: str, limit: int) -> List[Dict[str, Any]]:
    params = {"cameras": camera, "type": "motion", "limit": limit}
    data = api_get(base_url, "/api/review", params=params)
    return data if isinstance(data, list) else []


def main():
    args = parse_args()
    tz = ZoneInfo(args.timezone)

    items = review_items(args.base_url, args.camera, args.limit)
    filtered: List[Dict[str, Any]] = []

    for it in items:
        if it.get("event_id") is not None:
            continue
        st = it.get("start_time")
        if st is None:
            continue
        if args.start is not None and float(st) < float(args.start):
            continue
        if args.end is not None and float(st) > float(args.end):
            continue
        filtered.append(it)

    if not filtered:
        raise SystemExit("No motion-only review items matched.")

    lines = ["#EXTM3U\n"]
    for it in filtered:
        start = int(float(it["start_time"]))
        end_val = it.get("end_time")
        if end_val is None:
            end = start + int(args.default_duration)
        else:
            end = int(float(end_val))
            if end <= start:
                end = start + int(args.default_duration)

        start_local = datetime.fromtimestamp(start, tz=timezone.utc).astimezone(tz)
        end_local = datetime.fromtimestamp(end, tz=timezone.utc).astimezone(tz)
        title = f"{args.camera} {start_local.strftime('%Y-%m-%d %H:%M:%S %Z')} -> {end_local.strftime('%H:%M:%S %Z')}"
        duration = max(1, end - start)

        lines.append(f"#EXTINF:{duration},{title}\n")
        lines.append(f"{vod_url(args.base_url, args.camera, start, end)}\n")

    with open(args.out, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Wrote {len(filtered)} entries to {args.out}")


if __name__ == "__main__":
    main()
