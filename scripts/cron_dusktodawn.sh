#!/usr/bin/env bash
set -euo pipefail

# Cron-friendly wrapper for nightly dusktodawn export + upload.
# Configure via env vars or edit defaults below.

REPO_DIR="${REPO_DIR:-/home/gdupont/docker/frigate-commander}"
CAMERA="${CAMERA:-TapoC560WS}"
BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
OUT_DIR="${OUT_DIR:-${REPO_DIR}/montages}"
CLIENT_SECRET="${CLIENT_SECRET:-${REPO_DIR}/client_secret.json}"
TOKEN_PATH="${TOKEN_PATH:-${REPO_DIR}/tokens/account1.json}"
PRIVACY="${PRIVACY:-unlisted}"

DATE_STR="$(date -d "yesterday" +%F)"
TITLE="${TITLE:-${CAMERA} animals ${DATE_STR} dusktodawn}"

cd "${REPO_DIR}"

if [ -f "${REPO_DIR}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "${REPO_DIR}/.venv/bin/activate"
fi

PYTHON="${REPO_DIR}/.venv/bin/python"
if [ ! -x "${PYTHON}" ]; then
  PYTHON="python3"
fi

"${PYTHON}" frigate_montage.py \
  --base-url "${BASE_URL}" \
  --camera "${CAMERA}" \
  --dusktodawn \
  --date "${DATE_STR}" \
  --out-dir "${OUT_DIR}"

OUT_FILE="${OUT_DIR}/${CAMERA}-animals-${DATE_STR}-dusktodawn.mp4"
MANIFEST_FILE="${OUT_DIR}/${CAMERA}-animals-${DATE_STR}-dusktodawn.manifest.json"
CHAPTERS_FILE="${OUT_DIR}/${CAMERA}-animals-${DATE_STR}-dusktodawn-chapters.txt"

if [ ! -s "${OUT_FILE}" ]; then
  echo "Skip upload: output file missing or empty (${OUT_FILE})"
  exit 0
fi

if [ -f "${MANIFEST_FILE}" ]; then
  SEGMENTS_TOTAL="$("${PYTHON}" - <<'PY' "${MANIFEST_FILE}"
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("stats", {}).get("segments_total", 0))
PY
)"
  if [ "${SEGMENTS_TOTAL}" -le 0 ]; then
    echo "Skip upload: no segments in manifest (${MANIFEST_FILE})"
    exit 0
  fi
fi

UPLOAD_ARGS=(
  --client-secret "${CLIENT_SECRET}"
  --token "${TOKEN_PATH}"
  --file "${OUT_FILE}"
  --title "${TITLE}"
  --privacy "${PRIVACY}"
)
if [ -f "${CHAPTERS_FILE}" ]; then
  UPLOAD_ARGS+=(--description "$(cat "${CHAPTERS_FILE}")")
fi

"${PYTHON}" scripts/youtube_upload.py "${UPLOAD_ARGS[@]}"
