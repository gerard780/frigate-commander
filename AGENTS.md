# Repository Guidelines

## Project Structure & Module Organization

The project follows a 3-stage pipeline architecture:

```
frigate_segments.py  →  frigate_sources.py  →  frigate_render.py
     (events)              (disk/VOD)            (ffmpeg)
```

### Core Modules
- `frigate_segments.py` - Query Frigate API for detection events, apply filters, generate padded/merged segments.
- `frigate_sources.py` - Resolve segments to disk files or VOD URLs, emit manifest JSON.
- `frigate_render.py` - Build ffmpeg concat file, execute copy/encode/timelapse rendering.
- `frigate_montage.py` - Orchestrates all three stages plus playlist/chapters/upload.
- `frigate_timelapse.py` - Multi-day timelapse generator (no detection filtering).
- `frigate_motion_playlist.py` - Generate VLC playlist from motion-only review items.
- `utils.py` - Shared utilities (api_get, vod_url, atempo_chain, ffmpeg progress).

### Scripts
- `scripts/youtube_upload.py` - OAuth-based YouTube upload with token refresh.
- `scripts/cron_dusktodawn.sh` - Nightly cron wrapper for export + upload.

### Directories
- `montages/` - Default output directory for generated clips (override with `--out-dir`).
- `old/` - Legacy/archived scripts; avoid modifying unless restoring previous behavior.
- `__pycache__/` - Python bytecode; do not edit or commit.

## Setup & Dependencies
- Runtime: Python 3.10+ (uses `zoneinfo`).
- External tools: `ffmpeg` must be available on `PATH`.
- Python packages: `requests`, `astral`.
- Optional (YouTube upload): `google-api-python-client`, `google-auth-oauthlib`.
- Install: `pip install -r requirements.txt`

## Build, Test, and Development Commands

### Quick montage export
```bash
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --date 2025-12-30
```

### Run individual pipeline stages
```bash
# Stage 1: Generate segments JSON
python3 frigate_segments.py --camera TapoC560WS --dawntodusk --date 2025-12-30 > segments.json

# Stage 2: Resolve sources
python3 frigate_sources.py --segments-json segments.json > manifest.json

# Stage 3: Render video
python3 frigate_render.py --manifest-json manifest.json --out-dir ./montages
```

### Dry-run (validate without ffmpeg)
```bash
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --date 2025-12-30 --dry-run
```

### Timelapse
```bash
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50
```

## Coding Style & Naming Conventions
- Indentation: 4 spaces; keep lines readable.
- Style: prefer small helper functions and descriptive variable names (e.g., `window_after`, `merge_gap`).
- Keep CLI flags in `parse_args()` aligned with `Config` defaults.
- Type hints: use `List`, `Dict`, `Optional` from typing module.
- Dataclasses: use `@dataclass` for Config classes.

## Testing Guidelines
- No automated test suite is present (yet).
- Validate changes by running a small windowed export and confirming output.
- Use `--dry-run` to validate manifest and ffmpeg command without rendering.

## Commit & Pull Request Guidelines
- Commit history uses short, imperative summaries (e.g., "Add timelapse mode").
- Keep commits focused to a single change or feature.
- Update CHANGELOG.md for user-facing changes.

## Configuration & Safety Tips
- Verify `--base-url` and `--camera` match your Frigate instance.
- Review label filters with `--labels-include` / `--labels-exclude` or edit `Config.include_labels`.
- Default lat/lon is Shelbyville, KY; override in Config for accurate dawn/dusk.
- Recording path defaults to `/home/gdupont/docker/frigate/storage/recordings`; use `--recordings-path` to override.
