#!/usr/bin/env python3
"""
frigate_render.py

Responsible for ONE thing:
- Given a "source manifest" JSON (disk files and/or VOD urls),
  build a concat list and run ffmpeg to produce the final MP4.

It owns the important gotcha:
- concat list should be a REAL FILE, not stdin, or ffmpeg can treat paths as fd:/...
"""

import os
import argparse
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class Config:
    out_dir: str = "./montages"

    # Defaults: realtime exports (copy)
    default_copy: bool = True
    default_copy_audio: bool = True

    # VOD/concat protocols
    protocol_whitelist: str = "file,http,https,tcp,tls,crypto"

    # Encode defaults
    fps: int = 20
    nvenc_profile: str = "high"
    nvenc_rc: str = "vbr_hq"
    nvenc_bv: str = "0"
    gop_seconds: int = 3
    audio_rate: int = 48000
    default_encoder: str = "h264_nvenc"
    default_crf: int = 19

CFG = Config()


def atempo_chain_for_speed(speed: float):
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
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def run_ffmpeg_with_progress(cmd: List[str], total_out_seconds: float):
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
        if now - last_emit >= 10.0 and out_time_ms is not None:
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


def write_concat_file(out_dir: str, camera: str, entries: List[str]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f".concat_{camera}_{int(datetime.now().timestamp())}.txt")
    with open(path, "w", encoding="utf-8") as f:
        for line in entries:
            f.write(line)
    return path


def build_concat_entries(manifest: Dict[str, Any]) -> List[str]:
    """
    Flatten the manifest segment sources into concat demuxer 'file' lines.
    Dedup adjacent repeats.
    """
    entries: List[str] = []
    last = None
    for seg in manifest["segments"]:
        src = seg["source"]
        if src["type"] == "disk":
            for p in src["files"]:
                if p == last:
                    continue
                entries.append(f"file '{p}'\n")
                last = p
        else:
            u = src["url"]
            if u != last:
                entries.append(f"file '{u}'\n")
                last = u
    return entries


def run_ffmpeg(concat_path: str, out_mp4: str, *,
              copy_mode: bool, copy_audio: bool,
              timelapse: Optional[float],
              fps: int,
              preset: str,
              cq: int,
              encoder: str,
              crf: int,
              maxrate: str,
              bufsize: str,
              aq_strength: int,
              audio_bitrate: str,
              audio_channels: int,
              timelapse_audio: bool,
              progress: bool = False,
              total_out_seconds: Optional[float] = None):
    gop = int(CFG.gop_seconds) * int(fps)

    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", CFG.protocol_whitelist,
        "-f", "concat", "-safe", "0",
        "-i", concat_path,
    ]

    # timelapse always encodes
    if timelapse is not None:
        copy_mode = False
        copy_audio = False

    # video
    if copy_mode:
        cmd += ["-c:v", "copy"]
    else:
        if encoder in ("h264_nvenc", "hevc_nvenc"):
            cmd += [
                "-r", str(fps),
                "-c:v", encoder,
                "-preset", preset,
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
            if encoder == "h264_nvenc":
                cmd += ["-profile:v", CFG.nvenc_profile]
        elif encoder in ("libx264", "libx265"):
            cmd += [
                "-r", str(fps),
                "-c:v", encoder,
                "-preset", preset,
                "-crf", str(crf),
                "-g", str(gop),
            ]
        else:
            raise SystemExit(f"Unsupported encoder: {encoder}")

    if timelapse is not None:
        cmd += ["-filter:v", f"setpts=PTS/{timelapse}"]

    # audio
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
    if progress:
        run_ffmpeg_with_progress(cmd, float(total_out_seconds or 0.0))
    else:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if p.returncode != 0:
            print(p.stdout.decode("utf-8", errors="replace"))
            raise SystemExit("ffmpeg failed (see output above).")


def parse_args():
    p = argparse.ArgumentParser(description="Render montage from a sources manifest JSON.")
    p.add_argument("--manifest-json", required=True)

    p.add_argument("--out-dir", default=CFG.out_dir)
    p.add_argument("--out-file", default=None, help="Override output filename.")

    # mode
    p.add_argument("--copy", action="store_true", default=CFG.default_copy)
    p.add_argument("--copy-audio", action="store_true", default=CFG.default_copy_audio)
    p.add_argument("--encode", action="store_true", default=False)

    p.add_argument("--timelapse", type=float, default=None)
    p.add_argument("--timelapse-audio", action="store_true", default=False)
    p.add_argument("--progress", action="store_true", default=False)

    # encode params
    p.add_argument("--fps", type=int, default=CFG.fps)
    p.add_argument("--encoder", default=CFG.default_encoder,
                   choices=["h264_nvenc", "hevc_nvenc", "libx264", "libx265"])
    p.add_argument("--preset", default="p5")
    p.add_argument("--cq", type=int, default=23)
    p.add_argument("--crf", type=int, default=CFG.default_crf)
    p.add_argument("--maxrate", default="6M")
    p.add_argument("--bufsize", default="12M")
    p.add_argument("--aq-strength", type=int, default=8)

    # audio encode params
    p.add_argument("--audio-bitrate", default="96k")
    p.add_argument("--audio-channels", type=int, default=1)

    return p.parse_args()


def main():
    import json
    args = parse_args()

    with open(args.manifest_json, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # output filename default derived from manifest info
    cam = manifest["camera"]
    base_day = manifest["base_day"]
    base_day_end = manifest.get("base_day_end", base_day)
    window_tag = manifest["window_tag"]

    suffix = window_tag
    if args.timelapse is not None:
        suffix += f"-timelapse{args.timelapse}x"

    base_label = base_day
    if base_day_end != base_day:
        base_label = f"{base_day}_to_{base_day_end}"
    out_mp4 = args.out_file or os.path.join(args.out_dir, f"{cam}-animals-{base_label}-{suffix}.mp4")
    os.makedirs(args.out_dir, exist_ok=True)

    # Decide actual mode
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

    print(f"Mode:    {mode_str}")
    print(f"Output:  {out_mp4}")
    print(f"Stats:   segments={manifest['stats']['segments_total']} disk={manifest['stats']['disk_segments']} vod={manifest['stats']['vod_segments']} cadence≈{manifest['stats']['cadence']}s")

    concat_entries = build_concat_entries(manifest)
    concat_path = write_concat_file(args.out_dir, cam, concat_entries)
    print(f"Concat:  {concat_path} entries={len(concat_entries)}")

    total_out_seconds = sum([int(s["end"]) - int(s["start"]) for s in manifest["segments"]])
    if args.timelapse is not None:
        total_out_seconds = total_out_seconds / float(args.timelapse)

    run_ffmpeg(
        concat_path,
        out_mp4,
        copy_mode=copy_mode and not args.encode,
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
