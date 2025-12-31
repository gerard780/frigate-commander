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
import subprocess
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
    p.add_argument("--source", choices=["disk", "vod"], default="disk",
                   help="Choose a single source (no fallback). Default: disk.")
    p.add_argument("--start-slop", type=float, default=2.0)
    p.add_argument("--end-slop", type=float, default=4.0)

    # output
    p.add_argument("--out-dir", default=frigate_render.CFG.out_dir)
    p.add_argument("--out-file", default=None)
    p.add_argument("--playlist-out", default=None,
                   help="Write a VLC-compatible M3U playlist of VOD URLs.")
    p.add_argument("--playlist-only", action="store_true", default=False,
                   help="Only write playlist (skip rendering).")
    p.add_argument("--chapters-out", default=None,
                   help="Write YouTube chapter timestamps to a text file.")
    p.add_argument("--chapters-min", type=int, default=300,
                   help="Minimum chapter length in seconds (default 300).")
    p.add_argument("--chapters-gap", type=int, default=300,
                   help="Merge chapters when gap is below this many seconds (default 300).")

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

    return p.parse_args()


def format_chapter_ts(seconds: int) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def best_label_for_segment(seg_start: int, seg_end: int, events):
    counts = {}
    scores = {}
    for ev in events:
        label = ev.get("label")
        if not label or not isinstance(label, str):
            continue
        ev_start = ev.get("start_time")
        if ev_start is None:
            continue
        ev_end = ev.get("end_time") or ev_start
        if float(ev_start) > float(seg_end) or float(ev_end) < float(seg_start):
            continue
        counts[label] = counts.get(label, 0) + 1
        score = float(ev.get("top_score") or ev.get("score") or 0.0)
        scores[label] = max(scores.get(label, 0.0), score)

    if not counts:
        return "Animal"

    def sort_key(item):
        label, count = item
        return (count, scores.get(label, 0.0), label)

    return max(counts.items(), key=sort_key)[0]


def probe_duration(path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1",
        path,
    ]
    try:
        out = subprocess.check_output(cmd).decode("utf-8", errors="replace").strip()
        return float(out)
    except Exception:
        return 0.0


def build_segment_diagnostics(segments, events, tz, utc):
    cache = {}
    diagnostics = []
    durations = []
    prev_end = None

    for seg in segments:
        s = int(seg["start"]); e = int(seg["end"])
        src = seg["source"]
        est = max(1.0, float(e - s))

        if src["type"] == "disk":
            total = 0.0
            for p in src.get("files", []):
                if p not in cache:
                    cache[p] = probe_duration(p)
                total += cache[p]
            actual = max(1.0, total) if total > 0 else est
            file_count = len(src.get("files", []))
        else:
            actual = est
            file_count = 0

        gap_prev = None if prev_end is None else s - prev_end
        prev_end = e

        # Event overlap and padding info.
        ev_start = None
        ev_end = None
        label_counts = {}
        for ev in events:
            label = ev.get("label")
            if not label or not isinstance(label, str):
                continue
            st = ev.get("start_time")
            if st is None:
                continue
            et = ev.get("end_time") or st
            if float(st) > float(e) or float(et) < float(s):
                continue
            ev_start = float(st) if ev_start is None else min(ev_start, float(st))
            ev_end = float(et) if ev_end is None else max(ev_end, float(et))
            label_counts[label] = label_counts.get(label, 0) + 1

        pad_before = None
        pad_after = None
        if ev_start is not None:
            pad_before = float(s) - ev_start
        if ev_end is not None:
            pad_after = float(e) - ev_end

        start_local = datetime.fromtimestamp(s, tz=utc).astimezone(tz)
        end_local = datetime.fromtimestamp(e, tz=utc).astimezone(tz)

        diagnostics.append({
            "start": s,
            "end": e,
            "start_local": start_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "end_local": end_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "source": src["type"],
            "files": file_count,
            "est": est,
            "actual": actual,
            "diff": actual - est,
            "gap_prev": gap_prev,
            "pad_before": pad_before,
            "pad_after": pad_after,
            "labels": label_counts,
        })
        durations.append(actual)

    return durations, diagnostics


def build_chapters(segments, segment_durations, events, tz, utc, *, min_len: int, merge_gap: int):
    chapters = []
    current = None

    for seg, seg_duration in zip(segments, segment_durations):
        s = int(seg["start"]); e = int(seg["end"])
        label = best_label_for_segment(s, e, events)

        if current is None:
            current = {
                "start": s,
                "end": e,
                "label": label,
                "duration": max(1.0, float(seg_duration)),
                "segments": [(s, e, label)],
            }
            continue

        gap = s - current["end"]
        if gap <= int(merge_gap):
            current["end"] = max(current["end"], e)
            current["duration"] += max(1.0, float(seg_duration))
            current["segments"].append((s, e, label))
        else:
            chapters.append(current)
            current = {
                "start": s,
                "end": e,
                "label": label,
                "duration": max(1.0, float(seg_duration)),
                "segments": [(s, e, label)],
            }

    if current is not None:
        chapters.append(current)

    # Merge short chapters only when they are close to a neighbor.
    if chapters and int(min_len) > 0:
        merged = []
        i = 0
        while i < len(chapters):
            ch = chapters[i]
            if ch["duration"] >= int(min_len) or len(chapters) == 1:
                merged.append(ch)
                i += 1
                continue

            prev = merged[-1] if merged else None
            nxt = chapters[i + 1] if i + 1 < len(chapters) else None
            prev_gap = (ch["start"] - prev["end"]) if prev else None
            next_gap = (nxt["start"] - ch["end"]) if nxt else None

            can_merge_prev = prev is not None and prev_gap is not None and prev_gap <= int(merge_gap)
            can_merge_next = nxt is not None and next_gap is not None and next_gap <= int(merge_gap)

            if can_merge_prev or can_merge_next:
                if can_merge_prev and (not can_merge_next or prev_gap <= next_gap):
                    prev["end"] = max(prev["end"], ch["end"])
                    prev["duration"] += ch["duration"]
                    prev["segments"].extend(ch["segments"])
                    i += 1
                else:
                    nxt["start"] = min(nxt["start"], ch["start"])
                    nxt["duration"] += ch["duration"]
                    nxt["segments"] = ch["segments"] + nxt["segments"]
                    i += 1
            else:
                merged.append(ch)
                i += 1

        chapters = merged

    # Assign best label from combined segments.
    for ch in chapters:
        labels = [lbl for (_, _, lbl) in ch["segments"]]
        if labels:
            ch["label"] = max(set(labels), key=labels.count)

        start_local = datetime.fromtimestamp(ch["start"], tz=utc).astimezone(tz)
        ch["label_time"] = start_local.strftime("%H:%M:%S %Z")

    return chapters


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

    if args.no_disk:
        args.source = "vod"

    if args.source == "disk":
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
        if not disk_index:
            print("Disk-only: no recordings found; falling back to VOD for all segments.")
            args.source = "vod"

    disk_failures = []

    disk_failures = []

    for seg in segdoc["segments"]:
        s = int(seg["start"]); e = int(seg["end"])
        entry = {"start": s, "end": e}

        if args.source == "vod":
            used_vod += 1
            entry["source"] = {
                "type": "vod",
                "url": frigate_sources.vod_url(segdoc["base_url"], args.camera, s, e),
                "reason": "source=vod"
            }
        else:
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
                disk_failures.append((s, e, reason))

        if "source" in entry:
            manifest_segments.append(entry)

    if args.source == "disk" and disk_failures:
        print("Disk-only: skipped unresolved segments (showing first 10).")
        for s, e, reason in disk_failures[:10]:
            start_local = datetime.fromtimestamp(s, tz=utc).astimezone(tz)
            end_local = datetime.fromtimestamp(e, tz=utc).astimezone(tz)
            start_label = start_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            end_label = end_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            vod = frigate_sources.vod_url(segdoc["base_url"], args.camera, s, e)
            print(f"- {start_label} -> {end_label} ({s}-{e}) {reason}")
            print(f"  VOD: {vod}")

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

    base_stem = os.path.splitext(out_mp4)[0]
    segments_path = f"{base_stem}.segments.json"
    manifest_path = f"{base_stem}.manifest.json"

    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump(segdoc, f, indent=2)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if args.playlist_out:
        playlist_path = args.playlist_out
    else:
        playlist_path = f"{base_stem}.m3u"

    lines = ["#EXTM3U\n"]
    for seg in manifest_segments:
        s = int(seg["start"]); e = int(seg["end"])
        start_local = datetime.fromtimestamp(s, tz=utc).astimezone(tz)
        end_local = datetime.fromtimestamp(e, tz=utc).astimezone(tz)
        title = f"{args.camera} {start_local.strftime('%Y-%m-%d %H:%M:%S %Z')} -> {end_local.strftime('%H:%M:%S %Z')}"
        duration = max(1, e - s)
        vod = frigate_sources.vod_url(segdoc["base_url"], args.camera, s, e)
        lines.append(f"#EXTINF:{duration},{title}\n")
        lines.append(f"{vod}\n")
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Playlist: {playlist_path} entries={len(manifest_segments)}")

    if args.chapters_out:
        chapters_path = args.chapters_out
    else:
        chapters_path = f"{base_stem}-chapters.txt"

    offset = 0
    lines = []
    segment_durations, segment_debug = build_segment_diagnostics(manifest_segments, filtered, tz, utc)
    chapters = build_chapters(
        manifest_segments,
        segment_durations,
        filtered,
        tz,
        utc,
        min_len=args.chapters_min,
        merge_gap=args.chapters_gap,
    )
    for ch in chapters:
        lines.append(f"{format_chapter_ts(int(offset))} {ch['label']} {ch['label_time']}")
        offset += ch["duration"]
    with open(chapters_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Chapters: {chapters_path} entries={len(lines)}")

    debug_path = f"{base_stem}.debug.txt"
    total_est = sum(d["est"] for d in segment_debug)
    total_act = sum(d["actual"] for d in segment_debug)
    total_diff = total_act - total_est

    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"Output: {out_mp4}\n")
        f.write(f"Window: {segdoc['window']['start_local']} -> {segdoc['window']['end_local']} ({window_tag})\n")
        f.write(f"Params: pre_pad={args.pre_pad}s post_pad={args.post_pad}s merge_gap={args.merge_gap}s min_len={args.min_segment_len}s\n")
        f.write(f"Chapters: min={args.chapters_min}s gap={args.chapters_gap}s\n")
        f.write(f"Segments: total={len(segment_debug)} disk={used_disk} vod={used_vod} skipped={len(segment_debug) - used_disk - used_vod}\n")
        f.write(f"Duration: est={total_est:.2f}s actual={total_act:.2f}s delta={total_diff:+.2f}s\n")
        f.write("\n")
        for i, d in enumerate(segment_debug, 1):
            labels = ", ".join(
                [f"{k}={v}" for k, v in sorted(d["labels"].items(), key=lambda kv: (-kv[1], kv[0]))]
            )
            pad_before = f"{d['pad_before']:.2f}s" if d["pad_before"] is not None else "n/a"
            pad_after = f"{d['pad_after']:.2f}s" if d["pad_after"] is not None else "n/a"
            gap_prev = f"{d['gap_prev']}" if d["gap_prev"] is not None else "n/a"
            f.write(
                f"#{i:02d} {d['start_local']} -> {d['end_local']} src={d['source']} files={d['files']} "
                f"est={d['est']:.2f}s act={d['actual']:.2f}s diff={d['diff']:+.2f}s "
                f"gap_prev={gap_prev}s pad_before={pad_before} pad_after={pad_after} labels=[{labels}]\n"
            )
    print(f"Debug: {debug_path} entries={len(segment_debug)}")

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

    if args.playlist_only:
        print("Skipping render (--playlist-only).")
        return

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
