"""Format merged segments into a text timeline output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .frigate_api import normalize_event_times


@dataclass(frozen=True)
class TimelineSegment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _coerce_segment(segment: TimelineSegment | Mapping[str, float]) -> TimelineSegment:
    if isinstance(segment, TimelineSegment):
        return segment
    if not isinstance(segment, Mapping):
        raise TypeError("Segments must be TimelineSegment or mapping with start/end values.")
    if "start" not in segment or "end" not in segment:
        raise KeyError("Segment mapping must include 'start' and 'end' keys.")
    start = float(segment["start"])
    end = float(segment["end"])
    if end < start:
        start, end = end, start
    return TimelineSegment(start=start, end=end)


def _format_timecode(seconds: float) -> str:
    total = int(max(0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _collect_label_counts(events: Iterable[dict], segment: TimelineSegment) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        start, end = normalize_event_times(event)
        if end <= segment.start or start >= segment.end:
            continue
        label = str(event.get("label") or "").strip()
        sub_label = str(event.get("sub_label") or "").strip()
        if sub_label:
            label = f"{label}:{sub_label}" if label else sub_label
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    return counts


def build_timeline_entries(
    segments: Iterable[TimelineSegment | Mapping[str, float]],
    *,
    events: Iterable[dict] | None = None,
    combine_all: bool = False,
    include_labels: bool = True,
    include_counts: bool = True,
) -> list[str]:
    """Build timeline entries for merged segments.

    When combine_all is True, entry times are relative to the start of the combined output.
    """

    normalized = sorted((_coerce_segment(segment) for segment in segments), key=lambda seg: seg.start)
    entries: list[str] = []
    offset = 0.0
    for segment in normalized:
        start_time = offset if combine_all else segment.start
        entry = f"{_format_timecode(start_time)} - animal detection"
        if include_labels and events is not None:
            label_counts = _collect_label_counts(events, segment)
            if label_counts:
                if include_counts:
                    details = ", ".join(
                        f"{label}: {count}" for label, count in sorted(label_counts.items())
                    )
                else:
                    details = ", ".join(sorted(label_counts))
                entry = f"{entry} ({details})"
        entries.append(entry)
        if combine_all:
            offset += segment.duration
    return entries


def write_timeline_file(
    output_path: Path,
    segments: Iterable[TimelineSegment | Mapping[str, float]],
    *,
    events: Iterable[dict] | None = None,
    combine_all: bool = False,
    include_labels: bool = True,
    include_counts: bool = True,
) -> list[str]:
    """Write timeline entries to disk and return the entries."""

    entries = build_timeline_entries(
        segments,
        events=events,
        combine_all=combine_all,
        include_labels=include_labels,
        include_counts=include_counts,
    )
    output_path.write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    return entries
