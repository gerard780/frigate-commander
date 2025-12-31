frigate-commander notes

Feature list
- Event windowing with full-day or dawn/dusk modes, timezone-aware Astral calculations.
- Animal-only filtering with include/exclude labels and score thresholds.
- Segment padding, clamping, and merge-gap consolidation.
- Disk-first source resolution with UTC-based folder scanning and VOD fallback.
- Concat manifest generation and ffmpeg rendering with copy/encode/timelapse modes.
- One-shot orchestration of segments -> sources -> render.

Areas for improvement
- Add explicit --no-copy and --no-copy-audio flags for clearer mode control.
- Expose --limit in the wrapper to align event paging with segments mode.
- Emit a brief timezone/UTC summary in logs or manifest for easier debugging.
- Consider caching the disk index across runs for large windows.
- Add a dry-run mode to dump concat entries without invoking ffmpeg.
