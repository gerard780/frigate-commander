"""FFmpeg rendering helpers for Frigate recordings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import subprocess
import tempfile

from .sources import MediaSource


@dataclass(frozen=True)
class RenderSettings:
    mode: str
    output_mode: str
    encoder: str | None = None
    audio_codec: str | None = "copy"
    video_bitrate: str | None = None
    preset: str | None = None
    timelapse_speed: float = 8.0
    include_audio: bool = False
    extra_args: Sequence[str] = ()
    overwrite: bool = True


class RenderError(RuntimeError):
    """Raised when FFmpeg rendering fails."""


def _format_concat_entry(source: str) -> str:
    escaped = source.replace("'", "'\\''")
    return f"file '{escaped}'"


def _write_concat_file(sources: Iterable[MediaSource], directory: Path | None = None) -> Path:
    directory = directory or Path.cwd()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".ffconcat",
        prefix="concat_",
        dir=directory,
        delete=False,
        encoding="utf-8",
    ) as handle:
        for source in sources:
            handle.write(_format_concat_entry(source.source))
            handle.write("\n")
        return Path(handle.name)


def _build_base_command(concat_path: Path, settings: RenderSettings) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
    ]
    if settings.overwrite:
        command.append("-y")
    else:
        command.append("-n")

    command.extend([
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
    ])
    return command


def _build_codec_args(settings: RenderSettings) -> list[str]:
    mode = settings.mode.lower()
    args: list[str] = []

    if mode == "realtime":
        args.extend(["-c:v", "copy", "-c:a", "copy"])
    elif mode == "nvenc":
        encoder = settings.encoder or "h264_nvenc"
        args.extend(["-c:v", encoder])
        if settings.audio_codec:
            args.extend(["-c:a", settings.audio_codec])
        if settings.video_bitrate:
            args.extend(["-b:v", settings.video_bitrate])
        if settings.preset:
            args.extend(["-preset", settings.preset])
    elif mode == "timelapse":
        speed = settings.timelapse_speed
        if speed <= 0:
            raise ValueError("Timelapse speed must be greater than zero.")
        args.extend(["-filter:v", f"setpts=PTS/{speed}"])
        encoder = settings.encoder or "libx264"
        args.extend(["-c:v", encoder])
        if settings.video_bitrate:
            args.extend(["-b:v", settings.video_bitrate])
        if settings.preset:
            args.extend(["-preset", settings.preset])
        if settings.include_audio:
            if settings.audio_codec:
                args.extend(["-c:a", settings.audio_codec])
        else:
            args.append("-an")
    else:
        raise ValueError(f"Unsupported render mode: {settings.mode}")

    return args


def build_ffmpeg_command(
    sources: Sequence[MediaSource],
    output_path: Path,
    settings: RenderSettings,
    workdir: Path | None = None,
) -> tuple[list[str], Path]:
    concat_path = _write_concat_file(sources, directory=workdir)
    command = _build_base_command(concat_path, settings)
    command.extend(_build_codec_args(settings))
    command.extend(settings.extra_args)
    command.append(str(output_path))
    return command, concat_path


def run_ffmpeg(command: Sequence[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RenderError(f"FFmpeg exited with status {exc.returncode}.") from exc


def _build_segment_output_paths(
    output_path: Path,
    count: int,
) -> list[Path]:
    if count <= 0:
        return []
    if count == 1:
        return [output_path]

    stem = output_path.stem
    suffix = output_path.suffix
    return [output_path.with_name(f"{stem}_{index:03d}{suffix}") for index in range(1, count + 1)]


def render_segments(
    sources_by_segment: Sequence[Sequence[MediaSource]],
    output_path: Path,
    settings: RenderSettings,
    workdir: Path | None = None,
) -> list[Path]:
    """Render segments using FFmpeg and return created output paths."""

    if settings.output_mode not in {"separate", "combined"}:
        raise ValueError("output_mode must be 'separate' or 'combined'.")

    if settings.output_mode == "combined":
        flattened = [source for segment in sources_by_segment for source in segment]
        if not flattened:
            raise ValueError("No sources provided for combined render.")
        command, concat_path = build_ffmpeg_command(flattened, output_path, settings, workdir=workdir)
        try:
            run_ffmpeg(command)
        finally:
            concat_path.unlink(missing_ok=True)
        return [output_path]

    outputs = _build_segment_output_paths(output_path, len(sources_by_segment))
    rendered: list[Path] = []
    for sources, destination in zip(sources_by_segment, outputs):
        if not sources:
            continue
        command, concat_path = build_ffmpeg_command(sources, destination, settings, workdir=workdir)
        try:
            run_ffmpeg(command)
        finally:
            concat_path.unlink(missing_ok=True)
        rendered.append(destination)

    return rendered
