# Repository Guidelines

## Project Structure & Module Organization
- `frigate_daily_animal_montage_segments.py` is the primary script for generating daily animal montage segments from Frigate recordings and VOD.
- `montages/` is the default output directory for generated clips (can be overridden with `--out-dir`).
- `old/` contains legacy or archived content; avoid modifying unless you are explicitly restoring previous behavior.
- `__pycache__/` is Python bytecode output and should not be edited or committed.

## Setup & Dependencies
- Runtime: Python 3.10+ (uses `zoneinfo`).
- External tools: `ffmpeg` must be available on `PATH`.
- Python packages: `requests`, `astral`.
- Example install: `pip install requests astral`

## Build, Test, and Development Commands
- Run the script: `python3 frigate_daily_animal_montage_segments.py --camera TapoC560WS --dawntodusk`
- Use disk recordings: default `--recordings-path ~/docker/frigate/storage/recordings`.
- Force VOD-only: add `--no-disk`.
- Encode output: add `--encode` or `--timelapse 50` (implies encode).

## Coding Style & Naming Conventions
- Indentation: 4 spaces; keep lines readable and avoid overly long argument lists.
- Style: prefer small helper functions and clear, descriptive variable names (e.g., `window_after`, `merge_gap`).
- Keep CLI flags in `parse_args()` aligned with `Config` defaults.

## Testing Guidelines
- No automated test suite is present.
- Validate changes by running a small windowed export (e.g., `--date 2024-01-01 --dawntodusk --min-score 0.5`) and confirming output in `montages/`.

## Commit & Pull Request Guidelines
- Commit history uses short, imperative summaries (e.g., "Added Timelapse mode").
- Keep commits focused to a single change or feature.
- PRs should include a brief description, sample command used, and a note about expected output files (clip count/size).

## Configuration & Safety Tips
- Verify `--base-url` and `--camera` match your Frigate instance.
- Review label filters in `Config.include_labels` and `Config.exclude_labels` before running long exports.
