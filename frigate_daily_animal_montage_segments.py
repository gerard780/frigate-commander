#!/usr/bin/env python3
import os
import sys
import math
import shutil
import subprocess
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, date as date_cls
from zoneinfo import ZoneInfo

import requests
from astral import LocationInfo
from astral.sun import dawn, dusk


@dataclass
class Config:
    # ---- Frigate connection ----
    frigate_base: str = "http://127.0.0.1:5000"
    camera: str = "TapoC560WS"
    timezone_name: str = "America/New_York"

    # If your Frigate is behind auth/reverse-proxy, set one of these:
    # headers = {"Authorization": "Bearer <token>"}  OR  {"Authorization": "Basic ..."}
    headers: dict = None

    # ---- Shelbyville, KY defaults (for dawn/dusk) ----
    latitude: float = 38.2120
    longitude: float = -85.2230

    # ---- Animal label rules ----
    include_labels = {
        "bird",
        "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe",
        # common yard/farm add-ons (depends on your model)
        "deer", "raccoon", "squirrel", "rabbit", "fox", "coyote",
        "skunk", "opossum", "possum",
        "chipmunk", "groundhog", "bobcat", "mountain_lion", "cougar",
        "turkey"
    }
    exclude_labels = {
        "person", "car", "truck", "bus", "motorcycle", "bicycle",
        "package", "train", "boat", "airplane"
    }

    # Score filtering
    min_score: float = 0.0
    require_clip: bool = False  # keep False for time-range VOD montage

    # ---- Segment extraction / merging ----
    pre_pad: int = 5          # seconds before each detection
    post_pad: int = 5         # seconds after each detection
    merge_gap: int = 15       # merge segments that overlap OR are within this many seconds
    min_segment_len: int = 2  # ignore segments shorter than this (seconds)

    # ---- Output ----
    out_dir: str = "./montages"

    # ---- VOD endpoint template (HLS) ----
    vod_url_template: str = "{base}/vod/{camera}/start/{start}/end/{end}/master.m3u8"

    # ---- Default mode behavior ----
    # User requested: default to copy/copy-audio for normal realtime exports
    default_copy: bool = True
    default_copy_audio: bool = True

    # ---- NVENC settings (used when encoding) ----
    fps: int = 20
    nvenc_preset: str = "p5"       # p5 ~ x264 medium
    nvenc_profile: str = "high"
    nvenc_rc: str = "vbr_hq"

    # Size-reduction controls:
    nvenc_cq: int = 23
    nvenc_bv: str = "0"
    nvenc_maxrate: str = "6M"
    nvenc_bufsize: str = "12M"

    nvenc_aq_strength: int = 8    # 5-12 typical
    gop_seconds: int = 3          # GOP length in seconds (3s is good for wildlife clips)

    # ---- Audio (reduce size) ----
    audio_bitrate: str = "96k"     # 64k/96k/128k
    audio_channels: int = 1        # 1=mono (smaller), 2=stereo
    audio_rate: int = 48000        # keep standard


CFG = Config()


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def ensure_tools():
    if shutil.which("ffmpeg") is None:
        die("ffmpeg not found in PATH. Install ffmpeg.")
    try:
        import requests  # noqa: F401
    except Exception:
        die("Python 'requests' not installed. Try: pip install requests")
    try:
        import astral  # noqa: F401
    except Exception:
        die("astral not installed. Try: pip install astral")


def parse_args():
    p = argparse.ArgumentParser(
        description="Build an animal montage from Frigate detections -> padded time segments -> merged segments -> ffmpeg concat (HLS VOD)."
    )

    p.add_argument("--base-url", default=CFG.frigate_base)
    p.add_argument("--camera", default=CFG.camera)
    p.add_argument("--timezone", default=CFG.timezone_name)

    p.add_argument("--latitude", type=float, default=CFG.latitude)
    p.add_argument("--longitude", type=float, default=CFG.longitude)

    p.add_argument(
        "--date",
        default=None,
        help="YYYY-MM-DD. Default: yesterday (local TZ). Used as base day for dawn/dusk windows."
    )

    g = p.add_mutually_exclusive_group()
    g.add_argument("--dawntodusk", action="store_true",
                   help="Window = real dawn -> real dusk (base date).")
    g.add_argument("--dusktodawn", action="store_true",
                   help="Window = real dusk (base date) -> real dawn (next day).")

    # Segment behavior overrides
    p.add_argument("--pre-pad", type=int, default=CFG.pre_pad)
    p.add_argument("--post-pad", type=int, default=CFG.post_pad)
    p.add_argument("--merge-gap", type=int, default=CFG.merge_gap)
    p.add_argument("--min-segment-len", type=int, default=CFG.min_segment_len)
    p.add_argument("--min-score", type=float, default=CFG.min_score)

    # Output
    p.add_argument("--out-dir", default=CFG.out_dir)

    # ---- Mode control ----
    # Defaults (as requested) are copy+copy-audio, unless --timelapse is set.
    p.add_argument("--copy", action="store_true", default=CFG.default_copy,
                   help="Copy video stream (no re-encode). Default: ON for realtime exports.")
    p.add_argument("--copy-audio", action="store_true", default=CFG.default_copy_audio,
                   help="Copy audio stream. Default: ON for realtime exports.")
    p.add_argument("--encode", action="store_true", default=False,
                   help="Force encode mode (NVENC) even for realtime exports.")

    # ---- Timelapse ----
    p.add_argument("--timelapse", type=float, default=None,
                   help="Speed-up factor (e.g. 25, 50, 100, 4.2). Applies setpts=PTS/X. Forces encode mode.")
    p.add_argument("--timelapse-audio", action="store_true", default=False,
                   help="When using --timelapse, keep audio and speed it up via atempo chaining (often not useful).")

    # NVENC overrides (used when encoding)
    p.add_argument("--fps", type=int, default=CFG.fps)
    p.add_argument("--preset", default=CFG.nvenc_preset,
                   help="NVENC preset p1..p7 (p5 ~ x264 medium).")
    p.add_argument("--cq", type=int, default=CFG.nvenc_cq,
                   help="NVENC constant quality (lower=better, bigger files). Try 19..23.")
    p.add_argument("--maxrate", default=CFG.nvenc_maxrate)
    p.add_argument("--bufsize", default=CFG.nvenc_bufsize)
    p.add_argument("--aq-strength", type=int, default=CFG.nvenc_aq_strength)

    # Audio overrides (used when encoding audio)
    p.add_argument("--audio-bitrate", default=CFG.audio_bitrate)
    p.add_argument("--audio-channels", type=int, default=CFG.audio_channels)

    return p.parse_args()


def api_get(base_url: str, path: str, params=None):
    url = base_url.rstrip("/") + path
    r = requests.get(url, params=params, headers=CFG.headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def label_is_animal(label: str) -> bool:
    if label in CFG.exclude_labels:
        return False
    return label in CFG.include_labels


def compute_window(args, tz: ZoneInfo):
    """
    Returns (after_ts, before_ts, start_local_dt, end_local_dt, window_tag, base_day)
    base_day is the date used for naming (the --date day or yesterday).
    """
    now_local = datetime.now(tz)
    if args.date:
        base_day = date_cls.fromisoformat(args.date)
    else:
        base_day = (now_local - timedelta(days=1)).date()

    if args.dawntodusk or args.dusktodawn:
        loc = LocationInfo(
            name="Shelbyville",
            region="KY",
            timezone=args.timezone,
            latitude=args.latitude,
            longitude=args.longitude,
        )
        if args.dusktodawn:
            start_dt_local = dusk(loc.observer, date=base_day, tzinfo=tz)
            end_dt_local = dawn(loc.observer, date=base_day + timedelta(days=1), tzinfo=tz)
            window_tag = "dusktodawn"
        else:
            start_dt_local = dawn(loc.observer, date=base_day, tzinfo=tz)
            end_dt_local = dusk(loc.observer, date=base_day, tzinfo=tz)
            window_tag = "dawntodusk"
    else:
        start_dt_local = datetime(base_day.year, base_day.month, base_day.day, 0, 0, 0, tzinfo=tz)
        end_dt_local = start_dt_local + timedelta(days=1)
        window_tag = "fullday"

    after = int(start_dt_local.timestamp())
    before = int(end_dt_local.timestamp())
    return after, before, start_dt_local, end_dt_local, window_tag, base_day


def build_segments_from_events(events, window_after: int, window_before: int, pre_pad: int, post_pad: int, min_len: int):
    segments = []
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


def merge_segments(segments, merge_gap: int):
    if not segments:
        return []
    segments = sorted(segments, key=lambda x: x[0])
    merged = []
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


def vod_url_for_segment(base_url: str, camera: str, start: int, end: int) -> str:
    base = base_url.rstrip("/")
    return CFG.vod_url_template.format(base=base, camera=camera, start=start, end=end)


def probe_vod_url(url: str) -> bool:
    headers = CFG.headers or {}
    try:
        r = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        if 200 <= r.status_code < 300:
            return True
    except Exception:
        pass
    try:
        r = requests.get(url, headers=headers, timeout=10, stream=True, allow_redirects=True)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def atempo_chain_for_speed(speed: float):
    """
    FFmpeg atempo supports 0.5..2.0. For big speedups like 25x, chain multiple atempo=2.0.
    Returns a list of factors where each factor is within [0.5, 2.0] and product ~= speed.
    """
    if speed <= 0:
        raise ValueError("speed must be > 0")
    factors = []
    remaining = speed

    # Speedups > 2: repeatedly apply 2.0
    while remaining > 2.0 + 1e-9:
        factors.append(2.0)
        remaining /= 2.0

    # Now remaining in (0, 2]
    if remaining < 0.5 - 1e-9:
        # This would be slowdown too large; split into 0.5 chunks (not typical for timelapse)
        while remaining < 0.5 - 1e-9:
            factors.append(0.5)
            remaining /= 0.5

    # Add final factor if not ~1
    if abs(remaining - 1.0) > 1e-9:
        # Clamp just in case of floating error
        remaining = max(0.5, min(2.0, remaining))
        factors.append(remaining)

    return factors


def run_ffmpeg_concat_stdin(
    concat_text: bytes,
    out_mp4: str,
    *,
    fps: int,
    preset: str,
    cq: int,
    maxrate: str,
    bufsize: str,
    aq_strength: int,
    audio_bitrate: str,
    audio_channels: int,
    copy_mode: bool,
    copy_audio: bool,
    timelapse: float | None,
    timelapse_audio: bool,
):
    os.makedirs(os.path.dirname(out_mp4) or ".", exist_ok=True)
    gop = int(CFG.gop_seconds) * int(fps)

    # Base input
    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", "file,http,https,tcp,tls,pipe,fd,crypto",
        "-f", "concat", "-safe", "0",
        "-i", "-",  # concat list from stdin
    ]

    # Timelapse forces encode mode (copy + setpts is fragile across concat/HLS)
    if timelapse is not None:
        if timelapse <= 0:
            die("--timelapse must be > 0")
        copy_mode = False
        copy_audio = False  # default: drop audio unless timelapse_audio

    # Video
    if copy_mode:
        # Fast / minimal CPU: copy video.
        cmd += ["-c:v", "copy"]
        # If you want CFR output, you generally MUST re-encode; copy keeps original timestamps.
        # We'll avoid forcing -r in copy mode to prevent A/V drift or weird speed changes.
    else:
        cmd += [
            "-r", str(fps),
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-profile:v", CFG.nvenc_profile,
            "-rc:v", CFG.nvenc_rc,
            "-cq:v", str(cq),
            "-b:v", CFG.nvenc_bv,
            "-maxrate:v", str(maxrate),
            "-bufsize:v", str(bufsize),
            "-spatial-aq", "1",
            "-temporal-aq", "1",
            "-aq-strength", str(aq_strength),
            "-g", str(gop),
        ]

    # Filters for timelapse (video + optional audio)
    if timelapse is not None:
        cmd += ["-filter:v", f"setpts=PTS/{timelapse}"]

    # Audio
    if timelapse is not None and not timelapse_audio:
        cmd += ["-an"]
    else:
        if copy_mode and copy_audio:
            cmd += ["-c:a", "copy"]
        else:
            cmd += [
                "-c:a", "aac",
                "-b:a", str(audio_bitrate),
                "-ac", str(audio_channels),
                "-ar", str(CFG.audio_rate),
            ]

        if timelapse is not None and timelapse_audio:
            factors = atempo_chain_for_speed(float(timelapse))
            atempo = ",".join([f"atempo={f:.6f}".rstrip("0").rstrip(".") for f in factors])
            cmd += ["-filter:a", atempo]

    cmd += ["-movflags", "+faststart", out_mp4]

    print("Running:", " ".join(cmd))
    p = subprocess.run(cmd, input=concat_text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        print(p.stdout.decode("utf-8", errors="replace"))
        die("ffmpeg failed while reading the segment URLs. See output above.")


def main():
    ensure_tools()
    args = parse_args()
    tz = ZoneInfo(args.timezone)

    after, before, start_local, end_local, window_tag, base_day = compute_window(args, tz)

    # Decide mode:
    # - If --timelapse provided => encode mode forced
    # - Else if --encode => encode
    # - Else default copy/copy-audio (as requested)
    if args.timelapse is not None:
        copy_mode = False
        copy_audio = False
        mode_str = f"TIMELAPSE {args.timelapse}x (encode)"
    elif args.encode:
        copy_mode = False
        copy_audio = False
        mode_str = "ENCODE (forced)"
    else:
        copy_mode = bool(args.copy)
        copy_audio = bool(args.copy_audio)
        mode_str = f"COPY video={'yes' if copy_mode else 'no'} audio={'yes' if copy_audio else 'no'}"

    print(f"Camera:  {args.camera}")
    print(f"Window:  {start_local.isoformat()} -> {end_local.isoformat()} ({window_tag})")
    print(f"Epoch:   after={after} before={before}")
    print(f"Padding: pre={args.pre_pad}s post={args.post_pad}s merge_gap={args.merge_gap}s")
    print(f"Mode:    {mode_str}")

    if not copy_mode or args.timelapse is not None:
        print(f"NVENC:   fps={args.fps} preset={args.preset} cq={args.cq} maxrate={args.maxrate} bufsize={args.bufsize} aq_strength={args.aq_strength} gop={CFG.gop_seconds}s")
        if args.timelapse is not None:
            print(f"TL:      {args.timelapse}x (video setpts=PTS/{args.timelapse}) audio={'yes (atempo chain)' if args.timelapse_audio else 'no'}")
        else:
            print(f"Audio:   bitrate={args.audio_bitrate} channels={args.audio_channels}")

    # Pull events
    params = {"camera": args.camera, "after": after, "before": before, "limit": 5000}
    events = api_get(args.base_url, "/api/events", params=params)
    if not isinstance(events, list):
        die(f"Unexpected /api/events response: {type(events)}")

    # Filter animals
    filtered = []
    seen_labels = {}
    for ev in events:
        label = ev.get("label")
        if label:
            seen_labels[label] = seen_labels.get(label, 0) + 1

        if not label or not isinstance(label, str):
            continue
        if CFG.require_clip and not ev.get("has_clip"):
            continue

        score = float(ev.get("top_score") or ev.get("score") or 0.0)
        if score < float(args.min_score):
            continue

        if label_is_animal(label):
            filtered.append(ev)

    filtered.sort(key=lambda e: float(e.get("start_time") or 0.0))

    if not filtered:
        print("No matching animal detections found for that window.")
        if seen_labels:
            print("Labels seen in that window (all detections):")
            for k, v in sorted(seen_labels.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {k}: {v}")
        return

    segments = build_segments_from_events(filtered, after, before, args.pre_pad, args.post_pad, args.min_segment_len)
    merged = merge_segments(segments, args.merge_gap)

    print(f"Detections matched: {len(filtered)}")
    print(f"Raw segments:       {len(segments)}")
    print(f"Merged segments:    {len(merged)}")

    # Probe
    test_url = vod_url_for_segment(args.base_url, args.camera, merged[0][0], merged[0][1])
    print("Probe VOD URL:", test_url)
    if not probe_vod_url(test_url):
        die(
            "VOD probe failed. Your vod_url_template likely needs changing.\n"
            "Expected like:\n"
            "  /vod/<camera>/start/<start>/end/<end>/master.m3u8\n"
        )

    # Concat list
    lines = []
    total_seconds = 0
    for i, (s, e) in enumerate(merged, 1):
        url = vod_url_for_segment(args.base_url, args.camera, s, e)
        dur = e - s
        total_seconds += dur
        print(f"segment {i:03d}: {s}->{e} ({dur}s)")
        lines.append(f"file '{url}'\n")

    concat_text = "".join(lines).encode("utf-8")

    os.makedirs(args.out_dir, exist_ok=True)
    day_stamp = base_day.isoformat()
    suffix = window_tag
    if args.timelapse is not None:
        suffix += f"-timelapse{args.timelapse}x"
    out_mp4 = os.path.join(args.out_dir, f"{args.camera}-animals-{day_stamp}-{suffix}.mp4")

    print(f"Total montage source time (merged): ~{total_seconds}s")
    print(f"Output: {out_mp4}")

    run_ffmpeg_concat_stdin(
        concat_text,
        out_mp4,
        fps=args.fps,
        preset=args.preset,
        cq=args.cq,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
        aq_strength=args.aq_strength,
        audio_bitrate=args.audio_bitrate,
        audio_channels=args.audio_channels,
        copy_mode=copy_mode,
        copy_audio=copy_audio,
        timelapse=args.timelapse,
        timelapse_audio=args.timelapse_audio,
    )
    print("DONE:", out_mp4)


if __name__ == "__main__":
    main()
