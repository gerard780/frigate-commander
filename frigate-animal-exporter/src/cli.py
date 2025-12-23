from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Sequence

from config import DEFAULT_CONFIG_PATH, load_config



def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Frigate animal clips based on time range and rendering options."
    )
    parser.add_argument("--camera", required=True, help="Camera name to filter events.")
    parser.add_argument(
        "--start",
        required=True,
        help="Start timestamp (ISO-8601, e.g. 2024-01-01T12:00:00).",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End timestamp (ISO-8601, e.g. 2024-01-01T13:00:00).",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=2.0,
        help="Seconds of padding to include before/after clips.",
    )
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=5.0,
        help="Seconds between clips to merge into a single export.",
    )
    parser.add_argument(
        "--render-mode",
        choices=("original", "annotated"),
        default="annotated",
        help="Render mode for exported video.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file path for the exported video.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    return parser.parse_args(argv)



def _parse_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError(
            f"Invalid timestamp '{timestamp}'. Expected ISO-8601 format like 2024-01-01T12:00:00."
        ) from exc



def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config(args.config)

    start_time = _parse_timestamp(args.start)
    end_time = _parse_timestamp(args.end)

    if end_time <= start_time:
        raise ValueError("End time must be after start time.")

    print("Frigate Animal Exporter")
    print("========================")
    print(f"Camera: {args.camera}")
    print(f"Time range: {start_time.isoformat()} -> {end_time.isoformat()}")
    print(f"Padding: {args.padding}s")
    print(f"Merge gap: {args.merge_gap}s")
    print(f"Render mode: {args.render_mode}")
    print(f"Output: {args.output}")
    print(f"Frigate URL: {config.frigate_url}")
    print(f"Auth token set: {'yes' if config.auth_token else 'no'}")
    print(f"Recordings path: {config.recordings_path}")
    print()
    print("Next steps:")
    print("- Query Frigate events for the camera/time window")
    print("- Merge clips based on padding/merge gap")
    print("- Render/export to the output path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
