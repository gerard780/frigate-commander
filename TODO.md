# Frigate Commander - Feature Requests

## Completed Features

### ✅ VOD Support for Timelapses
- Added `--source` and `--base-url` arguments to `frigate_timelapse.py`
- Added `generate_vod_segments()` helper to create VOD URLs for time chunks
- VOD mode uses frame extraction approach (efficient for streaming)
- Updated web UI with source selector in timelapse options
- Updated backend worker to pass source/base_url arguments

### ✅ YouTube Upload Support
- Created `youtube_upload.py` - standalone script for YouTube uploads
- Uses YouTube Data API v3 with OAuth2 (requires one-time setup via Google Cloud Console)
- Added API endpoints: `/api/youtube/status` and `/api/youtube/upload`
- Added upload UI to Files page with title, description, and privacy settings
- Supports resumable uploads with progress tracking
- Dependencies: `google-api-python-client`, `google-auth-oauthlib`

**Setup Instructions:**
1. Go to https://console.cloud.google.com/
2. Create project, enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop application)
4. Download as `client_secrets.json` to project root
5. Run `python3 youtube_upload.py --setup` to authenticate

### ✅ YouTube Account Selection
- Added `/api/youtube/accounts` endpoint to list available token files
- Added `--token-file` argument to `youtube_upload.py`
- Added account selector dropdown in Files.tsx upload modal
- Accounts are auto-detected from `tokens/` directory

### ✅ More Job Options in Web UI
- Added **copy-only mode** for montage (skip re-encoding)
- Added **labels_exclude** field for montage filtering
- Added **min_score** threshold for detection confidence
- Added **custom start/end time** for time window (alternative to dawn/dusk)
- Added **dawn/dusk offsets** for timelapse time adjustments
- Added **CQ/CRF quality settings** for encoder control
- Added **CUDA checkbox** for GPU-accelerated frame extraction

### ✅ Preset Editing
- Added `PUT /api/presets/{id}` endpoint with `PresetUpdate` model
- Added `updatePreset()` API function in client.ts
- Added inline edit UI in Settings.tsx with Save/Cancel buttons

### ✅ All Motion Mode for Montages
- Added `--all-motion` flag to `frigate_montage.py`
- Uses Frigate's `/api/review` endpoint instead of `/api/events`
- Captures all motion triggers regardless of detection labels
- Added `all_motion` boolean to `MontageArguments` model
- Added checkbox in web UI: "Capture all motion (ignore detection labels)"
- Output files labeled as `{camera}-motion-...` instead of `{camera}-animals-...`

### ✅ Motion Intensity Filtering
- Added `--min-motion` parameter to filter by motion frame count
- Queries Frigate's `/api/{camera}/recordings` to get motion data per segment
- Sums motion frames from overlapping recording segments
- Only includes segments meeting the threshold
- Appears in web UI when "Capture all motion" is enabled

---

## Pending Features / Issues

### 1. Vite Dev Server Stability Issue
- App stops responding intermittently during development
- Ctrl+C or pressing 'r' to restart fixes it temporarily
- Doesn't stop in the same spot twice - seems random
- **TODO:** Investigate, may be HMR/WebSocket issue or memory leak

---

*Last updated: 2026-01-27*
