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

import frigate_segments
import frigate_sources
import frigate_render
from utils import atempo_chain_for_speed, format_duration, run_ffmpeg_with_progress


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
        parts = [f"setpts=PTS/{timelapse}"]
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
    p = argparse.ArgumentParser(description="Multi-day timelapse from Frigate disk recordings.")
    p.add_argument("--camera", required=True)
    p.add_argument("--recordings-path", default=frigate_sources.CFG.default_recordings_path)
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

    # output
    p.add_argument("--out-dir", default=CFG.out_dir)
    p.add_argument("--out-file", default=None)

    # timelapse / encode
    p.add_argument("--timelapse", type=float, default=CFG.default_timelapse)
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
        raise SystemExit(disk_err or "no recordings found")

    files = [p for (ts, p) in disk_index if after <= ts < before]
    if not files:
        raise SystemExit("no recordings within requested window")

    os.makedirs(args.out_dir, exist_ok=True)
    concat_path = frigate_render.write_concat_file(args.out_dir, args.camera, build_concat_entries(files))

    base_label = start_day.isoformat()
    if end_day != start_day:
        base_label = f"{start_day.isoformat()}_to_{end_day.isoformat()}"

    suffix = window_tag
    if args.timelapse is not None:
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
    output_seconds = window_seconds / float(args.timelapse)
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
    print(f"Window:  {start_local.isoformat()} -> {end_local.isoformat()} ({window_tag})")
    print(f"Files:   {len(files)} cadence≈{cadence}s")
    print(f"Concat:  {concat_path}")
    print(f"Output:  {out_mp4}")
    print(f"Codec:   {args.encoder} preset={preset} timelapse={args.timelapse}x fps={args.fps}")
    if args.scale:
        print(f"Scale:   {args.scale}")
    if args.cuda and args.encoder in ("hevc_nvenc", "h264_nvenc"):
        print("CUDA:    enabled (decode + scale_npp)")
    if spatial_aq or temporal_aq:
        aq_bits = []
        if spatial_aq:
            aq_bits.append(f"spatial aq={aq_strength}")
        if temporal_aq:
            aq_bits.append("temporal aq")
        print("AQ:      " + ", ".join(aq_bits))
    print(estimate_line)

    run_ffmpeg_with_progress(cmd, output_seconds)

    print("DONE:", out_mp4)


if __name__ == "__main__":
    main()
