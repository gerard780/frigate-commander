#!/usr/bin/env python3
"""
frigate_montage.py

Convenience wrapper:
- runs frigate_segments logic
- runs frigate_sources logic
- runs frigate_render logic

So you still do ONE command, but internally it’s separated and testable.
"""

import os
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import frigate_segments
import frigate_sources
import frigate_render


def parse_args():
    p = argparse.ArgumentParser(description="One-shot animal montage wrapper (segments -> sources -> render).")

    # Same args you’re used to:
    p.add_argument("--base-url", default=frigate_segments.CFG.base_url)
    p.add_argument("--camera", default=frigate_segments.CFG.camera)
    p.add_argument("--timezone", default=frigate_segments.CFG.timezone)

    p.add_argument("--latitude", type=float, default=frigate_segments.CFG.latitude)
    p.add_argument("--longitude", type=float, default=frigate_segments.CFG.longitude)

    p.add_argument("--date", default=None)
    p.add_argument("--start-date", default=None)
    p.add_argument("--end-date", default=None)
    p.add_argument("--days", type=int, default=None)

    g = p.add_mutually_exclusive_group()
    g.add_argument("--dawntodusk", action="store_true")
    g.add_argument("--dusktodawn", action="store_true")

    p.add_argument("--pre-pad", type=int, default=5)
    p.add_argument("--post-pad", type=int, default=5)
    p.add_argument("--merge-gap", type=int, default=15)
    p.add_argument("--min-segment-len", type=int, default=2)
    p.add_argument("--min-score", type=float, default=0.0)

    # disk
    p.add_argument("--recordings-path", default=frigate_sources.CFG.default_recordings_path)
    p.add_argument("--no-disk", action="store_true", default=False)
    p.add_argument("--start-slop", type=float, default=2.0)
    p.add_argument("--end-slop", type=float, default=4.0)

    # output
    p.add_argument("--out-dir", default=frigate_render.CFG.out_dir)
    p.add_argument("--out-file", default=None)

    # render mode
    p.add_argument("--copy", action="store_true", default=True)
    p.add_argument("--copy-audio", action="store_true", default=True)
    p.add_argument("--encode", action="store_true", default=False)
    p.add_argument("--timelapse", type=float, default=None)
    p.add_argument("--timelapse-audio", action="store_true", default=False)
    p.add_argument("--progress", action="store_true", default=False)

    # encode params
    p.add_argument("--fps", type=int, default=frigate_render.CFG.fps)
    p.add_argument("--preset", default="p5")
    p.add_argument("--cq", type=int, default=23)
    p.add_argument("--encoder", default=frigate_render.CFG.default_encoder,
                   choices=["h264_nvenc", "hevc_nvenc", "libx264", "libx265"])
    p.add_argument("--crf", type=int, default=frigate_render.CFG.default_crf)
    p.add_argument("--maxrate", default="6M")
    p.add_argument("--bufsize", default="12M")
    p.add_argument("--aq-strength", type=int, default=8)
    p.add_argument("--audio-bitrate", default="96k")
    p.add_argument("--audio-channels", type=int, default=1)

    # debug artifacts
    p.add_argument("--dump-json", action="store_true", default=False,
                   help="Write intermediate JSON to out-dir for debugging.")

    return p.parse_args()


def main():
    args = parse_args()

    # ---- Step A: build segments JSON (in-memory) ----
    tz = ZoneInfo(args.timezone)
    utc = ZoneInfo("UTC")
    after, before, start_local, end_local, window_tag, start_day, end_day = frigate_segments.compute_window(args, tz)

    events = frigate_segments.api_get(
        args.base_url, "/api/events",
        params={"camera": args.camera, "after": after, "before": before, "limit": 5000},
        headers=frigate_segments.CFG.headers
    )
    if not isinstance(events, list):
        raise SystemExit(f"Unexpected /api/events response: {type(events)}")

    filtered = []
    for ev in events:
        label = ev.get("label")
        if not label or not isinstance(label, str):
            continue
        score = float(ev.get("top_score") or ev.get("score") or 0.0)
        if score < float(args.min_score):
            continue
        if frigate_segments.label_is_animal(label):
            filtered.append(ev)

    raw_segments = frigate_segments.build_segments_from_events(
        filtered, after, before, args.pre_pad, args.post_pad, args.min_segment_len
    )
    merged = frigate_segments.merge_segments(raw_segments, args.merge_gap)

    segdoc = {
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
        "segments": [{"start": s, "end": e} for (s, e) in merged],
    }

    # ---- Step B: resolve sources (disk-first, VOD fallback) ----
    manifest_segments = []
    used_disk = 0
    used_vod = 0

    disk_index = []
    cadence = None
    disk_err = None

    if not args.no_disk:
        # Recordings folder structure is UTC-based; derive scan window from epoch seconds.
        start_utc = datetime.fromtimestamp(after, tz=utc)
        end_utc = datetime.fromtimestamp(before, tz=utc)
        disk_index, cadence, disk_err = frigate_sources.scan_index(
            args.recordings_path,
            args.camera,
            start_utc,
            end_utc,
            after,
            before,
            utc,
        )

    for seg in segdoc["segments"]:
        s = int(seg["start"]); e = int(seg["end"])
        entry = {"start": s, "end": e}

        if disk_index:
            chosen, reason = frigate_sources.find_files_for_segment(
                disk_index, cadence, s, e, args.start_slop, args.end_slop
            )
        else:
            chosen, reason = None, (disk_err or "disk disabled")

        if chosen:
            used_disk += 1
            entry["source"] = {"type": "disk", "files": [p for (_, p) in chosen], "cadence": cadence}
        else:
            used_vod += 1
            entry["source"] = {
                "type": "vod",
                "url": frigate_sources.vod_url(segdoc["base_url"], args.camera, s, e),
                "reason": reason
            }

        manifest_segments.append(entry)

    manifest = {
        "camera": args.camera,
        "base_url": segdoc["base_url"],
        "timezone": args.timezone,
        "window_tag": window_tag,
        "base_day": segdoc["base_day"],
        "base_day_end": segdoc.get("base_day_end", segdoc["base_day"]),
        "window": segdoc["window"],
        "segments": manifest_segments,
        "stats": {
            "segments_total": len(manifest_segments),
            "segments_skipped": len(disk_failures) if args.source == "disk" else 0,
            "disk_segments": used_disk,
            "vod_segments": used_vod,
            "disk_index_files": len(disk_index),
            "cadence": cadence,
        }
    }

    os.makedirs(args.out_dir, exist_ok=True)

    if args.dump_json:
        with open(os.path.join(args.out_dir, "segments.json"), "w", encoding="utf-8") as f:
            json.dump(segdoc, f, indent=2)
        with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # ---- Step C: render ----
    concat_entries = frigate_render.build_concat_entries(manifest)
    concat_path = frigate_render.write_concat_file(args.out_dir, args.camera, concat_entries)

    suffix = window_tag
    if args.timelapse is not None:
        suffix += f"-timelapse{args.timelapse}x"
    base_label = segdoc["base_day"]
    if segdoc.get("base_day_end") and segdoc["base_day_end"] != segdoc["base_day"]:
        base_label = f"{segdoc['base_day']}_to_{segdoc['base_day_end']}"
    out_mp4 = args.out_file or os.path.join(args.out_dir, f"{args.camera}-animals-{base_label}-{suffix}.mp4")

    # choose mode
    if args.timelapse is not None:
        copy_mode = False
        copy_audio = False
    elif args.encode:
        copy_mode = False
        copy_audio = False
    else:
        copy_mode = bool(args.copy)
        copy_audio = bool(args.copy_audio)

    print(f"Camera: {args.camera}")
    print(f"Window: {segdoc['window']['start_local']} -> {segdoc['window']['end_local']} ({window_tag})")
    print(f"Segments: disk={used_disk} vod_fallback={used_vod} cadence≈{cadence}s")
    print(f"Concat: {concat_path} entries={len(concat_entries)}")
    print(f"Output: {out_mp4}")

    total_out_seconds = sum([int(s["end"]) - int(s["start"]) for s in manifest_segments])
    if args.timelapse is not None:
        total_out_seconds = total_out_seconds / float(args.timelapse)

    frigate_render.run_ffmpeg(
        concat_path,
        out_mp4,
        copy_mode=copy_mode,
        copy_audio=copy_audio,
        timelapse=args.timelapse,
        fps=args.fps,
        preset=args.preset,
        cq=args.cq,
        encoder=args.encoder,
        crf=args.crf,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
        aq_strength=args.aq_strength,
        audio_bitrate=args.audio_bitrate,
        audio_channels=args.audio_channels,
        timelapse_audio=args.timelapse_audio,
        progress=args.progress,
        total_out_seconds=total_out_seconds,
    )

    print("DONE:", out_mp4)


if __name__ == "__main__":
    main()
