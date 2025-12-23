"""Helpers for querying Frigate events."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Iterable, Sequence

DEFAULT_ANIMAL_LABELS = (
    "bird",
    "cat",
    "cow",
    "deer",
    "dog",
    "fox",
    "horse",
    "mouse",
    "rabbit",
    "sheep",
)


def _normalize_base_url(base_url: str) -> str:
    if not base_url:
        raise ValueError("base_url is required")
    return base_url.rstrip("/") + "/"


def _build_events_url(
    base_url: str,
    camera: str | None,
    start_time: float | None,
    end_time: float | None,
    label: str | None,
    limit: int,
) -> str:
    query: dict[str, str] = {"limit": str(limit)}
    if camera:
        query["camera"] = camera
    if start_time is not None:
        query["after"] = str(start_time)
    if end_time is not None:
        query["before"] = str(end_time)
    if label:
        query["label"] = label
    url = urllib.parse.urljoin(_normalize_base_url(base_url), "api/events")
    return f"{url}?{urllib.parse.urlencode(query)}"


def _request_json(url: str) -> list[dict]:
    with urllib.request.urlopen(url) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("Unexpected response from Frigate events endpoint")
    return data


def _dedupe_events(events: Iterable[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for event in events:
        event_id = str(event.get("id", ""))
        if event_id:
            deduped[event_id] = event
        else:
            deduped[f"_anon_{len(deduped)}"] = event
    return list(deduped.values())


def fetch_animal_events(
    base_url: str,
    *,
    camera: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    labels: Sequence[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch events for the requested labels, camera, and time range.

    Args:
        base_url: Base URL for the Frigate instance, e.g. http://localhost:5000.
        camera: Optional camera name to filter events.
        start_time: Unix timestamp for the start of the window.
        end_time: Unix timestamp for the end of the window.
        labels: Optional labels to filter (defaults to common animal labels).
        limit: Max results per label request.
    """

    labels_to_fetch = tuple(labels) if labels is not None else DEFAULT_ANIMAL_LABELS
    if not labels_to_fetch:
        raise ValueError("labels must contain at least one label")

    events: list[dict] = []
    for label in labels_to_fetch:
        url = _build_events_url(base_url, camera, start_time, end_time, label, limit)
        events.extend(_request_json(url))

    return _dedupe_events(events)


def filter_events_by_labels(
    events: Iterable[dict],
    labels: Sequence[str],
) -> list[dict]:
    label_set = {label.lower() for label in labels}
    filtered = []
    for event in events:
        label = str(event.get("label", "")).lower()
        if label in label_set:
            filtered.append(event)
    return filtered


def normalize_event_times(event: dict) -> tuple[float, float]:
    start = float(event.get("start_time", 0.0))
    end = event.get("end_time")
    end_time = float(end) if end is not None else start
    return start, end_time
