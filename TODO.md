# Frigate Commander - Feature Requests

## Pending Features

### 1. VOD Support for Timelapses
- Currently timelapse only pulls from disk recordings
- Montage already has `--source` flag with `disk` and `vod` options
- Need to add similar VOD fallback logic to `frigate_timelapse.py`
- Update web UI JobNew.tsx to show source selector for timelapse jobs

### 2. YouTube Upload Support
- Add ability to upload completed videos directly to YouTube
- Options to consider:
  - Use YouTube Data API v3 with OAuth2
  - Add upload button on job completion / Files page
  - Auto-upload option in job settings
  - Title/description templates (camera name, date range, etc.)
  - Privacy setting (public/unlisted/private)
- Dependencies: `google-api-python-client`, `google-auth-oauthlib`

---

*Last updated: 2026-01-26*
