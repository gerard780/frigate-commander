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
# 3 days, 50x speed, encode with NVENC.
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder hevc_nvenc --fps 20 --cq 19

# Scale to 1080p height, preserve aspect ratio (CUDA scale for NVENC).
python3 frigate_timelapse.py --camera TapoC325WS --start-date 2025-12-01 --days 3 --timelapse 50 --encoder hevc_nvenc --fps 20 --cq 19 --scale -2:1080 --cuda

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

Notes
-----
- Disk recordings are preferred by default. VOD is used only if disk has no files.
- Missing segments are skipped but logged with local timestamps and VOD links.
- YouTube upload is optional; the cron wrapper skips upload on failures or empty outputs.
