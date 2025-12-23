"""Utilities for converting detections into normalized time segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from frigate_api import normalize_event_times


@dataclass(frozen=True)
class Segment:
    start: float
    end: float

    def with_padding(self, pre: float, post: float) -> "Segment":
        start = self.start - pre
        end = self.end + post
        if end < start:
            start, end = end, start
        return Segment(start=start, end=end)


def detections_to_segments(
    events: Iterable[dict],
    *,
    pre_pad: float = 0.0,
    post_pad: float = 0.0,
) -> list[Segment]:
    segments = []
    for event in events:
        start, end = normalize_event_times(event)
        segments.append(Segment(start=start, end=end).with_padding(pre_pad, post_pad))
    return segments


def merge_segments(segments: Iterable[Segment], merge_gap: float = 0.0) -> list[Segment]:
    sorted_segments = sorted(segments, key=lambda segment: segment.start)
    if not sorted_segments:
        return []

    merged = [sorted_segments[0]]
    for segment in sorted_segments[1:]:
        current = merged[-1]
        if segment.start <= current.end + merge_gap:
            merged[-1] = Segment(start=current.start, end=max(current.end, segment.end))
        else:
            merged.append(segment)
    return merged


def normalize_segments(segments: Iterable[Segment]) -> list[dict]:
    normalized = []
    for segment in segments:
        start = float(segment.start)
        end = float(segment.end)
        if end < start:
            start, end = end, start
        normalized.append({"start": start, "end": end})
    return normalized


def events_to_normalized_segments(
    events: Iterable[dict],
    *,
    pre_pad: float = 0.0,
    post_pad: float = 0.0,
    merge_gap: float = 0.0,
) -> list[dict]:
    segments = detections_to_segments(events, pre_pad=pre_pad, post_pad=post_pad)
    merged = merge_segments(segments, merge_gap=merge_gap)
    return normalize_segments(merged)
