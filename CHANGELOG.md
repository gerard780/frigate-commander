# Changelog
# All notable changes to this project are documented in this file.
#
# Format based on Keep a Changelog:
# https://keepachangelog.com/en/1.1.0/

## 2026-01-24
### Added
- Add `--sample-interval` for fast segment-level frame sampling timelapses.
  - Extracts first frame from each selected file (parallel processing with 16 workers).
  - Much faster than `--timelapse` for long periods (days/weeks/months).
  - Bucket-based selection ensures larger intervals are subsets of smaller ones.
- Add `--frame-sample` for frame-level sampling (1 frame per N seconds).
- Add `--frame-cache` for persistent frame caching across runs.
  - Defaults to `{out-dir}/frame_cache` when using `--sample-interval`.
  - Stores frames as WebP (~30% smaller than JPEG).
  - Timestamp-based paths: `cache/camera/YYYY-MM-DD/HH-MM-SS.webp`.
  - Overlapping time ranges reuse cached frames automatically.
- Add `--no-frame-cache` to disable caching if needed.
- Add terminal restoration on exit (fixes ffmpeg leaving terminal in bad state).
- Add multi-day dawn/dusk filtering for timelapses.
  - `--dawntodusk` with multi-day now only includes daytime periods from each day.
  - `--dusktodawn` with multi-day now only includes nighttime periods from each day.

### Changed
- Frame extraction now uses WebP format for better compression.

## 2026-01-17
### Added
- Add `--dry-run` flag to frigate_render.py and frigate_montage.py to validate without rendering.
- Add `--labels-include` and `--labels-exclude` flags for custom label filtering.
- Add troubleshooting section to README.md.
- Add retry logic with exponential backoff to Frigate API calls (utils.api_get).
- Add robust error handling to YouTube upload: token refresh, chunk retries, quota detection.
- Add graceful handling for empty segments (no matching events or failed source resolution).

### Changed
- Update AGENTS.md to reflect current module structure.
- Update ROADMAP.md with feature status and priorities.
- YouTube upload now uses 10MB chunks with resumable upload for reliability.

### Fixed
- Restore configurable `vod_url_template` in frigate_sources.py that was lost during utils extraction.
- Fix incorrect flag names in README (`--pre-pad`/`--post-pad`, not `--pre-padding`/`--post-padding`).

## 2025-12-31
### Added
- Support multi-day windows in segment generation.
- Add multi-day timelapse generator.
- Generate VLC playlist for motion-only review items.
- Add roadmap notes.
### Changed
- Support multi-day windows in montage outputs.
- Add encoder selection and ffmpeg progress output.
- Default to disk-only sources and log skipped segments.
- Auto-generate playlists, chapters, and debug reports for montage runs.
### Fixed
- Fix render progress time import.

## 2025-12-30
### Changed
- Fix UTC disk scanning.
### Misc
- Simplify legacy montage script copy/encode flags and remove timelapse handling.

## 2025-12-16
### Added
- Initial import.
- Added Timelapse mode.
