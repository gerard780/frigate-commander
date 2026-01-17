# Changelog
# All notable changes to this project are documented in this file.
#
# Format based on Keep a Changelog:
# https://keepachangelog.com/en/1.1.0/

## 2026-01-17
### Added
- Add `--dry-run` flag to frigate_render.py and frigate_montage.py to validate without rendering.
- Add `--labels-include` and `--labels-exclude` flags for custom label filtering.
- Add troubleshooting section to README.md.

### Changed
- Update AGENTS.md to reflect current module structure.
- Update ROADMAP.md with feature status and priorities.

### Fixed
- Restore configurable `vod_url_template` in frigate_sources.py that was lost during utils extraction.

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
