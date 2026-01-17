# Frigate Commander Roadmap

## Current Features

### Core Pipeline
- [x] 3-stage architecture: segments → sources → render
- [x] Event windowing with full-day, dawn/dusk, or custom time ranges
- [x] Multi-day window support (--start-date, --end-date, --days)
- [x] Animal-only filtering with include/exclude labels and score thresholds
- [x] CLI label overrides (--labels-include, --labels-exclude)
- [x] Segment padding, clamping, and merge-gap consolidation
- [x] Disk-first source resolution with UTC-based folder scanning
- [x] VOD fallback with configurable URL template
- [x] Concat manifest generation and ffmpeg rendering

### Rendering
- [x] Copy mode (no re-encode)
- [x] Encode mode with encoder selection (h264_nvenc, hevc_nvenc, libx264, libx265)
- [x] Timelapse mode with audio time-scaling (atempo chain)
- [x] NVENC AQ defaults (spatial + temporal)
- [x] CUDA decode/scale option for timelapse
- [x] FFmpeg progress output
- [x] Dry-run mode (validate without ffmpeg)

### Output
- [x] MP4 with faststart for streaming
- [x] VLC-compatible M3U playlist
- [x] YouTube chapter timestamps
- [x] Debug report with segment diagnostics
- [x] Segment and manifest JSON for debugging

### Integrations
- [x] Frigate API (/api/events, /api/review)
- [x] YouTube upload with OAuth token refresh
- [x] Astral library for dawn/dusk calculations
- [x] Cron wrapper for nightly automation

## In Progress

### Quality of Life
- [ ] Config file support (.yaml) for per-camera settings
- [ ] Structured logging with --verbose flag

## Planned

### High Priority
- [ ] Unit tests (pytest) for window computation, label filtering, cadence logic
- [x] API retry logic with exponential backoff
- [ ] Disk index caching across runs

### Medium Priority
- [ ] Resume from segment (--resume-from-segment) for partial failures
- [ ] Webhook notifications on completion
- [ ] Thumbnail extraction (first frame per segment)
- [ ] Multi-camera montage (merge segments from multiple cameras)

### Low Priority
- [ ] SQLite event cache to avoid re-querying Frigate
- [ ] Web dashboard (Flask UI)
- [ ] Frigate+ API integration for enhanced labels

## Completed (Recent)

### 2026-01-17
- [x] Restore configurable vod_url_template
- [x] Add --dry-run mode
- [x] Add --labels-include / --labels-exclude CLI flags
- [x] Update documentation (AGENTS.md, ROADMAP.md, README.md)
- [x] Add API retry logic with exponential backoff
- [x] Add YouTube upload error handling (token refresh, chunk retries, quota detection)
- [x] Add graceful empty segment handling with diagnostic output

### 2026-01-16
- [x] Extract shared utils.py module
- [x] Add YouTube token refresh

### 2025-12-31
- [x] Multi-day window support
- [x] Multi-day timelapse generator
- [x] Motion-only playlist generator
- [x] Auto-generate playlists, chapters, debug reports

## Ideas / Future Consideration

- Per-camera VOD URL templates in config
- Event deduplication across overlapping segments
- Automatic quality selection based on source resolution
- Integration with Home Assistant for notifications
- Export presets (quick/standard/high-quality)
