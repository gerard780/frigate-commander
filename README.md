Frigate Commander
=================

Utilities for generating animal montage videos and multi-day timelapses from
Frigate recordings and VOD, plus helper scripts for motion-only playlists and
YouTube uploads.

Requirements
------------
- Python 3.10+
- ffmpeg on PATH
- Python deps: requests, astral (plus YouTube upload deps if used)

Install
-------
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt

Quick Start: Animal Montage
---------------------------
# Dawntodusk for a single day.
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --date 2025-12-31

# Dusktodawn for yesterday (useful for nightly exports).
python3 frigate_montage.py --camera TapoC560WS --dusktodawn --date 2025-12-30

# Preview playlist only (no MP4 render).
python3 frigate_montage.py --camera TapoC560WS --dusktodawn --date 2025-12-30 --playlist-only

# Use a different Frigate base URL.
python3 frigate_montage.py --base-url http://192.168.15.194:5000 --camera KC420WS --dusktodawn --date 2025-12-30

# Exact time window (local time).
python3 frigate_montage.py --camera TapoC560WS --start-time 2025-01-08T14:45:00 --end-time 2025-01-08T15:00:00

# Use VOD only (disk is default).
python3 frigate_montage.py --source vod --camera TapoC560WS --dusktodawn --date 2025-12-30

# Export with encode + progress.
python3 frigate_montage.py --camera TapoC560WS --dusktodawn --date 2025-12-30 --encode --progress

Outputs (same base name as MP4)
-------------------------------
- Playlist preview: *.m3u
- Chapters text: *-chapters.txt
- Segment/manifest JSON: *.segments.json and *.manifest.json
- Concat file (ffmpeg): .concat_*.txt
- Debug file: *-debug.txt

Multi-Day Window Examples
-------------------------
# Last 3 days starting from 2025-12-01.
python3 frigate_montage.py --camera TapoC560WS --start-date 2025-12-01 --days 3

# Explicit date range.
python3 frigate_montage.py --camera TapoC560WS --start-date 2025-12-01 --end-date 2025-12-04

Timelapse (multi-day)
---------------------
# 3 days, 50x speed, encode with NVENC (AQ enabled by default).
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder hevc_nvenc --fps 20 --cq 19

# Scale to 1080p height, preserve aspect ratio (CUDA scale for NVENC).
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder hevc_nvenc --fps 20 --cq 19 --scale -2:1080 --cuda

# Disable AQ if needed.
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder hevc_nvenc --fps 20 --cq 19 --spatial-aq 0 --temporal-aq 0

# Software encode (libx265) with CRF.
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder libx265 --crf 23

Motion-Only VLC Playlist (Review API)
-------------------------------------
# Generates an M3U from motion-only review items (no detection).
python3 frigate_motion_playlist.py --base-url http://127.0.0.1:5000 --camera TapoC560WS --start 1767209000 --end 1767211000 --out montages/motion_only.m3u

YouTube Upload Script
---------------------
# Upload a finished montage.
python3 scripts/youtube_upload.py --client-secret ./client_secret.json --token ./tokens/account1.json --file ./montages/TapoC560WS-animals-2025-12-30-dusktodawn.mp4 --title "TapoC560WS animals 2025-12-30"

# Dry run (no upload).
python3 scripts/youtube_upload.py --client-secret ./client_secret.json --token ./tokens/account1.json --file ./montages/TapoC560WS-animals-2025-12-30-dusktodawn.mp4 --title "TapoC560WS animals 2025-12-30" --dry-run

# Authorize a new account (creates a new token file).
python3 scripts/youtube_upload.py --client-secret ./client_secret.json --token ./tokens/account2.json --file ./montages/TapoC560WS-animals-2025-12-30-dusktodawn.mp4 --title "Auth check" --dry-run

Cron Wrapper (nightly export + upload)
--------------------------------------
# One-off run.
BASE_URL=http://192.168.15.194:5000 CAMERA=KC420WS ./scripts/cron_dusktodawn.sh

# Environment variables:
# REPO_DIR, CAMERA, BASE_URL, OUT_DIR, CLIENT_SECRET, TOKEN_PATH, PRIVACY, TITLE

Dry-Run Mode
------------
Validate your configuration without rendering:
```bash
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --date 2025-12-30 --dry-run
```
This will query the API, resolve sources, build the concat file, and print the ffmpeg command without executing it.

Custom Label Filters
--------------------
Override the default animal labels:
```bash
# Only include specific animals
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --labels-include bird,cat,dog

# Exclude specific labels (in addition to defaults)
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --labels-exclude squirrel,rabbit

# Combine both
python3 frigate_montage.py --camera TapoC560WS --dawntodusk --labels-include bird,cat --labels-exclude person
```

Troubleshooting
---------------

### No segments found / empty output
- Check that your camera name matches exactly: `--camera` is case-sensitive.
- Verify the Frigate base URL is reachable: `curl http://127.0.0.1:5000/api/events?limit=1`
- Ensure events exist in the time window. Try `--date` with a known active day.
- Check label filters: use `--labels-include` to broaden or verify `Config.include_labels`.

### VOD probe failed
- The VOD URL returned a non-2xx status. Check that Frigate VOD is accessible.
- Verify the base URL doesn't have a trailing slash issue.
- If using a reverse proxy, ensure `/vod/` paths are forwarded correctly.
- Custom VOD URL? Edit `CFG.vod_url_template` in `frigate_sources.py`.

### Disk-only: no recordings found
- Verify `--recordings-path` points to your Frigate recordings folder.
- Check folder structure: `recordings/YYYY-MM-DD/HH/<camera>/MM.SS.mp4`
- Recordings folder uses UTC timestamps, not local time.
- Try `--source vod` to bypass disk and use VOD URLs directly.

### ffmpeg errors
- "Protocol not found": Add protocols to whitelist in `frigate_render.py` Config.
- "Invalid data": Corrupt segment file. Check disk for bad recordings.
- "No such file": Disk file was deleted between source resolution and render.
- Use `--dry-run` to see the exact ffmpeg command being generated.

### Dawn/dusk times are wrong
- Default lat/lon is Shelbyville, KY. Edit `Config.latitude` and `Config.longitude` in `frigate_segments.py`.
- Verify timezone: `--timezone America/New_York` (uses IANA timezone names).

### YouTube upload fails
- Token expired? The script now auto-refreshes. Delete old token and re-auth if issues persist.
- Check `--client-secret` path points to valid OAuth credentials JSON.
- Quota exceeded? YouTube API has daily upload limits.

### Segments are too short or too long
- Adjust `--pre-padding` and `--post-padding` (default 2 seconds each).
- Adjust `--merge-gap` to consolidate nearby segments (default 5 seconds).
- Use `--min-score` to filter low-confidence detections.

### Performance issues
- Large time windows scan many disk folders. Consider `--source vod` for speed.
- NVENC encoding is faster than software (libx264/libx265).
- Use `--timelapse` to reduce output duration for long recordings.

Notes
-----
- Disk recordings are preferred by default. VOD is used only if disk has no files.
- Missing segments are skipped but logged with local timestamps and VOD links.
- YouTube upload is optional; the cron wrapper skips upload on failures or empty outputs.
