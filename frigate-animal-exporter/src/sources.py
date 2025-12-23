"""Utilities for resolving Frigate recording sources for FFmpeg concat.

Expected Frigate recordings layout
==================================

Frigate stores recording segments using a deterministic directory structure. This
module assumes the following layout under the recordings directory::

    recordings_dir/
      <camera>/
        YYYY-MM-DD/
          HH/
            MM/
              <start_unix>-<end_unix>.mp4

Where:
* ``<camera>`` is the camera name from Frigate configuration.
* ``YYYY-MM-DD`` is the UTC date of the recording start.
* ``HH`` is the 24-hour clock hour (zero-padded).
* ``MM`` is the minute (zero-padded).
* ``<start_unix>`` and ``<end_unix>`` are epoch timestamps in seconds.

If your recordings directory differs, update :func:`parse_recording_path` to
match the naming convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
import urllib.request


@dataclass(frozen=True)
class Segment:
    """Represents a requested recording segment."""

    camera: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RecordingFile:
    """Metadata for a local recording file."""

    path: Path
    start_ts: int
    end_ts: int


@dataclass(frozen=True)
class MediaSource:
    """A media source to pass to FFmpeg concatenation."""

    source: str
    start_ts: int
    end_ts: int
    source_type: str  # "file" or "vod"


def parse_recording_path(path: Path) -> Optional[RecordingFile]:
    """Parse a Frigate recording file path into timestamps.

    Returns None if the path does not match the expected naming convention.
    """

    if path.suffix != ".mp4":
        return None

    name_parts = path.stem.split("-")
    if len(name_parts) != 2:
        return None

    try:
        start_ts = int(name_parts[0])
        end_ts = int(name_parts[1])
    except ValueError:
        return None

    return RecordingFile(path=path, start_ts=start_ts, end_ts=end_ts)


def _to_epoch_seconds(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def locate_local_recordings(
    recordings_dir: Path,
    segment: Segment,
) -> List[RecordingFile]:
    """Locate local recording files that overlap the requested segment."""

    camera_dir = recordings_dir / segment.camera
    if not camera_dir.exists():
        return []

    start_ts = _to_epoch_seconds(segment.start)
    end_ts = _to_epoch_seconds(segment.end)

    matches: List[RecordingFile] = []
    for path in camera_dir.rglob("*.mp4"):
        recording = parse_recording_path(path)
        if not recording:
            continue
        if recording.end_ts <= start_ts or recording.start_ts >= end_ts:
            continue
        matches.append(recording)

    return sorted(matches, key=lambda rec: rec.start_ts)


def detect_gaps(
    segment: Segment,
    recordings: Sequence[RecordingFile],
) -> List[Tuple[int, int]]:
    """Detect missing time ranges for a segment.

    Returns a list of (gap_start, gap_end) epoch second tuples.
    """

    start_ts = _to_epoch_seconds(segment.start)
    end_ts = _to_epoch_seconds(segment.end)

    if not recordings:
        return [(start_ts, end_ts)]

    merged: List[Tuple[int, int]] = []
    for recording in sorted(recordings, key=lambda rec: rec.start_ts):
        if not merged:
            merged.append((recording.start_ts, recording.end_ts))
            continue
        last_start, last_end = merged[-1]
        if recording.start_ts <= last_end:
            merged[-1] = (last_start, max(last_end, recording.end_ts))
        else:
            merged.append((recording.start_ts, recording.end_ts))

    gaps: List[Tuple[int, int]] = []
    cursor = start_ts
    for rec_start, rec_end in merged:
        if rec_start > cursor:
            gaps.append((cursor, min(rec_start, end_ts)))
        cursor = max(cursor, rec_end)
        if cursor >= end_ts:
            break

    if cursor < end_ts:
        gaps.append((cursor, end_ts))

    return [(gap_start, gap_end) for gap_start, gap_end in gaps if gap_end > gap_start]


def build_vod_url(base_url: str, camera: str, start_ts: int, end_ts: int) -> str:
    """Build a Frigate /vod URL for a camera and time range."""

    base = base_url.rstrip("/")
    return f"{base}/vod/{camera}/start/{start_ts}/end/{end_ts}"


def request_vod_segments(
    base_url: str,
    camera: str,
    gaps: Iterable[Tuple[int, int]],
    timeout: float = 10.0,
) -> List[str]:
    """Issue Frigate /vod requests for missing gaps.

    Returns the list of generated VOD URLs.
    """

    urls: List[str] = []
    for gap_start, gap_end in gaps:
        url = build_vod_url(base_url, camera, gap_start, gap_end)
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout):
            pass
        urls.append(url)
    return urls


def build_media_sources(
    recordings_dir: Path,
    segment: Segment,
    frigate_url: str,
) -> List[MediaSource]:
    """Build a unified, ordered list of media sources for a segment."""

    recordings = locate_local_recordings(recordings_dir, segment)
    gaps = detect_gaps(segment, recordings)
    vod_urls = request_vod_segments(frigate_url, segment.camera, gaps) if gaps else []

    sources: List[MediaSource] = []
    for recording in recordings:
        sources.append(
            MediaSource(
                source=str(recording.path),
                start_ts=recording.start_ts,
                end_ts=recording.end_ts,
                source_type="file",
            )
        )
    for (gap_start, gap_end), url in zip(gaps, vod_urls):
        sources.append(
            MediaSource(
                source=url,
                start_ts=gap_start,
                end_ts=gap_end,
                source_type="vod",
            )
        )

    return sorted(sources, key=lambda item: item.start_ts)


def build_sources_for_segments(
    recordings_dir: Path,
    segments: Sequence[Segment],
    frigate_url: str,
) -> List[List[MediaSource]]:
    """Build ordered media sources for multiple segments."""

    return [build_media_sources(recordings_dir, segment, frigate_url) for segment in segments]
